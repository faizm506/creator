import math
import os
import re
from datetime import timedelta
from urllib.parse import quote_plus

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login, logout
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import IntegrityError, transaction
from django.db.models import Count, F, Q, Sum
from django.core.cache import cache
from django.http import FileResponse, Http404, HttpResponse, HttpResponseRedirect, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from .context import inbox_total

from .forms import (BoostForm, CampaignForm, OfferForm, PhotoForm, ProfileForm, ProposalForm, ReviewForm,
                    ShowcaseForm, SignupForm)
from .models import (NICHES, RANK_ORDER, BoostRequest, Campaign, Message, Offer, Profile, Review, ShopPhoto,
                     ShowcasePost, refresh_rating, waiting_for)
from .utils import client_ip, hit, qr_svg, throttle, upi_link


def not_found(request, exception):
    return render(request, "core/404.html", status=404)


def _creators():
    return Profile.objects.filter(role=Profile.CREATOR).select_related("user")


def _brands():
    return Profile.objects.filter(role=Profile.BRAND).select_related("user")


def featured_shelf(request, limit=4, **filters):
    """Boosted creators, rotated fairly: whoever has been shown least goes first.
    Needs a bio, niche and followers so paid spots never show empty pages."""
    qs = (_creators().filter(boost_until__gt=timezone.now(), followers__gt=0, **filters)
          .exclude(bio="").exclude(niche="").order_by("boost_impressions", *RANK_ORDER))
    if not settings.BOOST_ENABLED:
        return []
    shelf = list(qs[:limit])
    for p in shelf:  # count one impression per visitor per 30 minutes
        if hit(f"imp:{client_ip(request)}:{p.pk}", 1800) == 1:
            Profile.objects.filter(pk=p.pk).update(boost_impressions=F("boost_impressions") + 1)
    return shelf


def niche_champions():
    best = {}
    for p in _creators().exclude(niche="").order_by(*RANK_ORDER)[:400]:
        best.setdefault(p.niche, p)
    return [(k, label, best.get(k)) for k, label in NICHES if k != "other"]


def slots_info(p):
    cap = settings.FEATURED_SLOTS_PER_NICHE
    active = Profile.objects.filter(role=Profile.CREATOR, niche=p.niche, boost_until__gt=timezone.now())
    used = active.count()
    soonest = active.order_by("boost_until").values_list("boost_until", flat=True).first()
    return {"cap": cap, "used": used, "left": max(0, cap - used), "soonest": soonest}


def how(request):
    return render(request, "core/how.html", {"cap": settings.FEATURED_SLOTS_PER_NICHE})


def _mix(*groups, pattern=(0, 0, 1, 2)):
    """Interleave creators, campaigns and brands so the feed feels varied."""
    iters = [iter(g) for g in groups]
    out, done = [], [False] * len(iters)
    while not all(done):
        for idx in pattern:
            if idx >= len(iters) or done[idx]:
                continue
            try:
                out.append(next(iters[idx]))
            except StopIteration:
                done[idx] = True
        if len(out) > 40:
            break
    return out


def home(request):
    feed = request.GET.get("feed", "all")
    if feed not in ("all", "creators", "brands", "campaigns"):
        feed = "all"
    creators = list(_creators().prefetch_related("showcase").order_by(*RANK_ORDER)[:20])
    brands = list(_brands().prefetch_related("photos").annotate(
        open_count=Count("user__campaigns", filter=Q(user__campaigns__is_open=True), distinct=True)
    ).order_by(*RANK_ORDER)[:10])
    campaigns = list(Campaign.objects.filter(is_open=True).select_related("brand__profile").annotate(
        n_apps=Count("offers", filter=Q(offers__initiator="creator"), distinct=True)).order_by("-created")[:10])
    c_items = [{"kind": "creator", "p": p, "rank": i + 1} for i, p in enumerate(creators[:12])]
    b_items = [{"kind": "brand", "p": p, "rank": i + 1} for i, p in enumerate(brands[:8])]
    k_items = [{"kind": "campaign", "c": c} for c in campaigns[:8]]
    if feed == "creators":
        items = c_items
    elif feed == "brands":
        items = b_items
    elif feed == "campaigns":
        items = k_items
    else:
        items = _mix(c_items, b_items, k_items, pattern=(0, 0, 2, 0, 1, 2))
    stories = []
    for i in range(max(len(creators[:9]), len(brands[:4]))):
        if i < len(creators[:9]):
            stories.append(creators[i])
        if i < len(brands[:4]) and i % 2 == 1:
            stories.append(brands[i])
    me = request.user.profile if request.user.is_authenticated else None
    return render(request, "core/home.html", {
        "feed": feed, "items": items, "stories": stories, "niches": [n for n in NICHES if n[0] != "other"],
        "rail_creators": creators[:5], "rail_brands": brands[:3],
        "me": me, "my_info": rank_info(me) if me else None,
    })


@throttle("signup", limit=8, window=3600)
def signup(request):
    if request.user.is_authenticated:
        return redirect("settings")
    form = SignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        messages.success(request, "Welcome! Complete your profile to start ranking.")
        return redirect("settings")
    return render(request, "registration/signup.html", {"form": form})


class LoginView(auth_views.LoginView):
    """Slows password guessing: 8 wrong tries per account or 15 per IP locks sign-in for 15 minutes."""
    template_name = "registration/login.html"
    redirect_authenticated_user = True

    def _keys(self):
        who = re.sub(r"[^a-z0-9._]", "", self.request.POST.get("username", "").strip().lower())[:40]
        return f"lf:ip:{client_ip(self.request)}", f"lf:u:{who}"

    def post(self, request, *args, **kwargs):
        ip_key, user_key = self._keys()
        if cache.get(ip_key, 0) >= 15 or cache.get(user_key, 0) >= 8:
            messages.error(request, "Too many wrong tries. For your safety, wait 15 minutes or reset your password.")
            return redirect("login")
        return super().post(request, *args, **kwargs)

    def form_invalid(self, form):
        for k in self._keys():
            hit(k, 900)
        return super().form_invalid(form)

    def form_valid(self, form):
        cache.delete(self._keys()[1])
        return super().form_valid(form)


def leaderboard(request):
    kind = "brands" if request.GET.get("kind") == "brands" else "creators"
    niche = request.GET.get("niche", "")
    city = request.GET.get("city", "").strip()[:60]
    q = request.GET.get("q", "").strip()[:60]
    qs = _brands() if kind == "brands" else _creators()
    if niche in dict(NICHES):
        qs = qs.filter(niche=niche)
    else:
        niche = ""
    if city:
        qs = qs.filter(city__icontains=city)
    if q:
        qs = qs.filter(Q(handle__icontains=q) | Q(display_name__icontains=q))
    page = Paginator(qs.order_by(*RANK_ORDER), 20).get_page(request.GET.get("page"))
    fl = {}
    if niche:
        fl["niche"] = niche
    if city:
        fl["city__icontains"] = city
    featured = featured_shelf(request, 3, **fl) if kind == "creators" and page.number == 1 and not q else []
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "core/leaderboard.html", {
        "page": page, "featured": featured, "niches": NICHES, "niche": niche, "city": city, "q": q,
        "qs": params.urlencode(), "kind": kind,
    })


def rank_info(p):
    """Rank among people of the same kind (creators or brands), in their city and niche, with the leaderboard's tie-breaks."""
    base = Profile.objects.filter(role=p.role)
    total = base.count()
    ahead = base.filter(
        Q(rank_score__gt=p.rank_score)
        | Q(rank_score=p.rank_score, followers__gt=p.followers)
        | Q(rank_score=p.rank_score, followers=p.followers, created__lt=p.created)
    )
    overall = ahead.count() + 1
    return {
        "overall": overall, "total": total,
        "city": ahead.filter(city__iexact=p.city).count() + 1 if p.city else None,
        "niche": ahead.filter(niche=p.niche).count() + 1 if p.niche else None,
        "top_pct": max(1, math.ceil(overall / total * 100)) if total else 100,
    }


def earned_badges(p, info):
    b = []
    if p.verified:
        b.append("Verified shop" if p.is_brand else "Verified creator")
    if info["overall"] <= 10:
        b.append("Top 10 brand" if p.is_brand else "Top 10 overall")
    if p.city and info["city"] and info["city"] <= 10:
        b.append(f"#{info['city']} in {p.city}")
    if not p.is_brand and p.niche and info["niche"] and info["niche"] <= 3:
        b.append(f"Top 3 in {p.get_niche_display()}")
    if p.rating_count >= 3 and p.rating_avg >= 4.5:
        b.append("Top rated")
    if p.deals_done >= 3:
        b.append(f"{p.deals_done} jobs done")
    if p.is_brand:
        if p.photos.count() >= 3:
            b.append("Photo-ready shop")
    else:
        if (timezone.now() - p.created).days <= 30 and p.rank_score >= 40:
            b.append("Rising star")
        if p.showcase.count() >= 3:
            b.append("Showcase ready")
    if p.completeness == 100:
        b.append("Complete profile")
    if p.is_boosted:
        b.append("Featured")
    return b


def creator_detail(request, handle):
    p = get_object_or_404(Profile.objects.select_related("user"), handle=handle.lower())
    is_owner = request.user.is_authenticated and request.user.pk == p.user_id
    if not is_owner:  # count one view per visitor session
        seen = request.session.get("seen", [])
        if p.handle not in seen:
            Profile.objects.filter(pk=p.pk).update(views=F("views") + 1)
            request.session["seen"] = (seen + [p.handle])[-60:]
            p.views += 1
    info = rank_info(p)
    ctx = {
        "p": p, "info": info, "badges": earned_badges(p, info), "is_owner": is_owner,
        "reviews": Review.objects.filter(subject=p.user).select_related("author__profile")[:10],
        "can_contact": bool(p.whatsapp) and request.user.is_authenticated and (p.show_contact or _connected(request.user, p.user)),
    }
    if p.is_brand:
        place = ", ".join(x for x in (p.address, p.city) if x)
        ctx.update({
            "photos": p.photos.all(), "campaigns": p.user.campaigns.filter(is_open=True)[:4],
            "map_q": quote_plus(place) if p.address else "",
        })
        return render(request, "core/brand.html", ctx)
    similar = []
    if p.niche:
        similar = _creators().filter(niche=p.niche).exclude(pk=p.pk).order_by(*RANK_ORDER)[:3]
    ctx.update({"showcase": p.showcase.all(), "similar": similar, "rate": p.suggested_rate})
    return render(request, "core/creator.html", ctx)


def _connected(a, b):
    """True when two users have an accepted or completed offer between them."""
    return Offer.objects.filter(status__in=[Offer.ACCEPTED, Offer.COMPLETED]).filter(
        Q(brand=a, creator=b) | Q(brand=b, creator=a)).exists()


def ig_go(request, handle):
    """Counts a visit, then sends the person to the creator's Instagram (fixed destination, no open redirect)."""
    p = get_object_or_404(Profile, handle=handle.lower())
    if hit(f"igclick:{client_ip(request)}:{p.pk}", 3600) == 1:
        Profile.objects.filter(pk=p.pk).update(ig_clicks=F("ig_clicks") + 1)
    return HttpResponseRedirect(f"https://www.instagram.com/{p.handle}/")


def _dash_stats(user, profile):
    hired = Offer.objects.filter(Q(brand=user) | Q(creator=user), status__in=[Offer.ACCEPTED, Offer.COMPLETED]).count()
    stats = {"waiting": waiting_for(user).count(), "hired": hired}
    if profile.is_brand:
        stats["sent"] = Offer.objects.filter(brand=user, initiator="brand").count()
        stats["campaigns"] = Campaign.objects.filter(brand=user, is_open=True).count()
    return stats


@never_cache
@login_required
def settings_view(request):
    profile = request.user.profile
    form = ProfileForm(request.POST or None, instance=profile)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Saved. Your profile just got 3% more irresistible.")
        return redirect("settings")
    pending = request.user.boost_requests.filter(status=BoostRequest.PENDING).exists()
    return render(request, "core/settings.html", {
        "form": form, "p": profile, "info": rank_info(profile), "pending": pending,
        "steps": profile.next_steps, "stats": _dash_stats(request.user, profile),
        "showcase": profile.showcase.all(), "photos": profile.photos.all(),
        "reviews": Review.objects.filter(subject=request.user).select_related("author__profile")[:5],
    })


@login_required
@require_POST
@throttle("showcase", limit=20, window=3600)
def showcase_add(request):
    p = request.user.profile
    if not p.is_creator:
        return redirect("settings")
    form = ShowcaseForm(request.POST, profile=p)
    if not form.is_valid():
        messages.error(request, form.errors["url"][0])
    elif p.showcase.count() >= 6:
        messages.error(request, "You can showcase up to 6 posts. Remove one to add another.")
    else:
        _, made = ShowcasePost.objects.get_or_create(profile=p, code=form.code, defaults={"kind": form.kind})
        p.save()  # refresh score
        messages.success(request, "Reel added. Instant glow-up." if made else "That one is already in your showcase.")
    return redirect(reverse("settings") + "#showcase")


@login_required
@require_POST
def showcase_remove(request, pk):
    p = request.user.profile
    get_object_or_404(ShowcasePost, pk=pk, profile=p).delete()
    p.save()
    messages.success(request, "Removed from your showcase.")
    return redirect(reverse("settings") + "#showcase")


@login_required
@throttle("boost", limit=6, window=3600)
def boost(request):
    if not settings.BOOST_ENABLED:
        raise Http404
    profile = request.user.profile
    plans = []
    for key, (label, price, days) in settings.BOOST_PLANS.items():
        link = upi_link(price, f"Boost @{profile.handle}")
        plans.append({"key": key, "label": label, "price": price, "days": days, "link": link, "qr": qr_svg(link)})
    form = BoostForm(request.POST or None)
    slots = slots_info(profile) if profile.niche else None
    blocked = ""
    if not profile.is_creator:
        blocked = "Boosting is for creator accounts."
    elif not profile.niche:
        blocked = "Choose your niche in your dashboard first. Featured spots are sold per niche."
    elif slots["left"] == 0 and not profile.is_boosted:
        blocked = "All Featured spots in your niche are taken right now."
    if request.method == "POST":
        if blocked:
            messages.error(request, blocked)
        elif request.user.boost_requests.filter(status=BoostRequest.PENDING).count() >= 3:
            messages.error(request, "You already have 3 requests waiting for review.")
        elif form.is_valid():
            label, price, days = settings.BOOST_PLANS[form.cleaned_data["plan"]]
            BoostRequest.objects.create(
                user=request.user, plan=form.cleaned_data["plan"], amount=price, days=days, utr=form.cleaned_data["utr"],
            )
            messages.success(request, "Payment submitted. Your boost starts once we confirm it, usually within a day.")
            return redirect("boost")
    history = request.user.boost_requests.all()[:10]
    return render(request, "core/boost.html", {
        "plans": plans, "form": form, "p": profile, "history": history, "upi_id": settings.UPI_ID,
        "slots": slots, "blocked": blocked,
    })


def campaign_list(request):
    qs = Campaign.objects.filter(is_open=True).select_related("brand__profile").annotate(n_apps=Count("offers", filter=Q(offers__initiator="creator")))
    niche = request.GET.get("niche", "")
    if niche in dict(NICHES):
        qs = qs.filter(niche=niche)
    else:
        niche = ""
    sort = "budget" if request.GET.get("sort") == "budget" else "new"
    qs = qs.order_by("-budget" if sort == "budget" else "-created")
    page = Paginator(qs, 12).get_page(request.GET.get("page"))
    return render(request, "core/campaigns.html", {"page": page, "niches": NICHES, "niche": niche, "sort": sort})


@login_required
def campaign_new(request):
    if request.user.profile.role != Profile.BRAND:
        messages.error(request, "Only brand accounts can post campaigns.")
        return redirect("campaigns")
    form = CampaignForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        c = form.save(commit=False)
        c.brand = request.user
        c.save()
        messages.success(request, "Campaign posted. Now watch the proposals roll in (or at least one polite hello).")
        return redirect("campaign", pk=c.pk)
    return render(request, "core/campaign_form.html", {"form": form})


def campaign_detail(request, pk):
    c = get_object_or_404(Campaign.objects.select_related("brand__profile"), pk=pk)
    user = request.user
    is_owner = user.is_authenticated and c.brand_id == user.id
    proposals_qs = Offer.objects.filter(campaign=c, initiator="creator").select_related("creator__profile")
    mine = None
    if user.is_authenticated and not is_owner:
        mine = proposals_qs.filter(creator=user).first()
    applied = bool(mine and mine.is_open)
    is_creator = user.is_authenticated and user.profile.role == Profile.CREATOR
    more = Campaign.objects.filter(is_open=True).exclude(pk=c.pk).select_related("brand__profile")
    if c.niche:
        more = more.filter(niche=c.niche)
    return render(request, "core/campaign.html", {
        "c": c, "is_owner": is_owner, "proposals": proposals_qs if is_owner else [], "mine": mine, "applied": applied,
        "can_apply": is_creator and c.is_open and not applied, "form": ProposalForm(initial={"budget": c.budget}),
        "n_apps": proposals_qs.count(), "more": more[:2],
    })


@login_required
@require_POST
@throttle("apply", limit=20, window=3600)
def campaign_apply(request, pk):
    """A creator sends the brand a proposal with their own price. The brand accepts or declines it."""
    c = get_object_or_404(Campaign, pk=pk, is_open=True)
    if request.user.profile.role != Profile.CREATOR:
        messages.error(request, "Only creator accounts can send proposals.")
        return redirect("campaign", pk=pk)
    form = ProposalForm(request.POST)
    if not form.is_valid():
        err = next(iter(form.errors.values()))[0]
        messages.error(request, err)
        return redirect("campaign", pk=pk)
    if Offer.objects.filter(campaign=c, creator=request.user, initiator="creator",
                            status__in=[Offer.PENDING, Offer.ACCEPTED]).exists():
        messages.info(request, "You already sent a proposal for this campaign.")
        return redirect("campaign", pk=pk)
    o = Offer.objects.create(
        brand=c.brand, creator=request.user, campaign=c, initiator="creator", title=c.title,
        deliverables=c.deliverables, budget=form.cleaned_data["budget"], message=form.cleaned_data["message"],
    )
    messages.success(request, "Proposal sent. Now we wait, like a group chat after \"we should totally meet up\".")
    return redirect("offer", pk=o.pk)


@login_required
@require_POST
def campaign_close(request, pk):
    c = get_object_or_404(Campaign, pk=pk, brand=request.user)
    c.is_open = False
    c.save(update_fields=["is_open"])
    messages.success(request, "Campaign closed.")
    return redirect("campaign", pk=pk)


# ---------- security ----------
@login_required
@require_POST
def logout_others(request):
    from django.contrib.sessions.models import Session
    mine, n = str(request.user.pk), 0
    for s in Session.objects.filter(expire_date__gt=timezone.now()):
        if s.session_key != request.session.session_key and s.get_decoded().get("_auth_user_id") == mine:
            s.delete()
            n += 1
    messages.success(request, f"Signed out of {n} other device{'s' if n != 1 else ''}.")
    return redirect(reverse("settings") + "#security")


@login_required
@require_POST
@throttle("delete", limit=5, window=3600)
def delete_account(request):
    u = request.user
    if u.is_staff:
        messages.error(request, "Staff accounts are removed from the admin panel.")
    elif not u.check_password(request.POST.get("password", "")):
        messages.error(request, "That password is not correct, so nothing was deleted.")
    else:
        logout(request)
        u.delete()
        messages.success(request, "Your account and data were deleted.")
        return redirect("home")
    return redirect(reverse("settings") + "#security")


# ---------- hiring ----------
def _offer_or_404(request, pk):
    o = get_object_or_404(Offer.objects.select_related("brand__profile", "creator__profile", "campaign"), pk=pk)
    if request.user.pk not in (o.brand_id, o.creator_id):
        raise Http404
    return o


@login_required
@throttle("offer", limit=15, window=86400)
def offer_new(request, handle):
    """Brand hires a creator, or a creator pitches a brand. Same form, opposite directions."""
    target = get_object_or_404(Profile.objects.select_related("user"), handle=handle.lower())
    me = request.user.profile
    if target.user_id == request.user.pk:
        return redirect("settings")
    if me.role == target.role:
        messages.error(request, "Brands hire creators, and creators pitch brands.")
        return redirect("creator", handle=target.handle)
    by_creator = me.role == Profile.CREATOR
    brand_user = target.user if by_creator else request.user
    creator_user = request.user if by_creator else target.user
    dup = Offer.objects.filter(brand=brand_user, creator=creator_user, initiator=me.role, status=Offer.PENDING).first()
    if dup:
        messages.info(request, "You already have a pending offer here.")
        return redirect("offer", pk=dup.pk)
    initial = {}
    cid = request.GET.get("campaign", "")
    if cid.isdigit():
        c = Campaign.objects.filter(pk=cid, brand=brand_user, is_open=True).first()
        if c:
            initial = {"campaign": c, "title": c.title, "deliverables": c.deliverables, "budget": c.budget}
    form = OfferForm(request.POST or None, brand=brand_user, by_creator=by_creator, initial=initial)
    if request.method == "POST" and form.is_valid():
        o = form.save(commit=False)
        o.brand, o.creator, o.initiator = brand_user, creator_user, me.role
        o.save()
        messages.success(request, f"Sent to {target.display_name}. You'll see their reply in your inbox.")
        return redirect("offer", pk=o.pk)
    return render(request, "core/offer_form.html", {
        "form": form, "t": target, "by_creator": by_creator, "rate": target.suggested_rate if not by_creator else None,
    })


def _is_initiator(o, user):
    return ("brand" if user.pk == o.brand_id else "creator") == o.initiator


@never_cache
@login_required
def offer_detail(request, pk):
    o = _offer_or_404(request, pk)
    o.messages.filter(read=False).exclude(sender=request.user).update(read=True)
    is_brand = request.user.pk == o.brand_id
    is_init = _is_initiator(o, request.user)
    other_user = o.creator if is_brand else o.brand
    other = other_user.profile
    thread = [{"id": 0, "mine": is_init, "body": o.message, "at": o.created, "first": True}]
    thread += [{"id": m.pk, "mine": m.sender_id == request.user.pk, "body": m.body, "at": m.created, "first": False}
               for m in o.messages.all()]
    return render(request, "core/offer.html", {
        "o": o, "thread": thread, "is_brand": is_brand, "is_init": is_init, "other": other,
        "reveal": o.status in (Offer.ACCEPTED, Offer.COMPLETED) and bool(other.whatsapp),
        "my_review": Review.objects.filter(author=request.user, subject=other_user).first(),
        "their_review": Review.objects.filter(author=other_user, subject=request.user).first(),
        "review_form": ReviewForm(),
    })


ACTION_MESSAGES = {
    "accept": "Deal! You can both see each other's WhatsApp number now. Try not to leave them on read.",
    "decline": "Declined. Politely, we hope.",
    "withdraw": "Withdrawn. We never saw anything.",
    "complete": "Work finished. Time for honest reviews (be nice, but be true).",
}


@login_required
@require_POST
def offer_action(request, pk, action):
    """Whoever did not start the offer can accept or decline it. The starter can withdraw it while it waits.
    Either side can mark accepted work as finished."""
    if action not in ACTION_MESSAGES:
        raise Http404
    with transaction.atomic():
        o = _offer_or_404(request, pk)
        o = Offer.objects.select_for_update().select_related("brand__profile", "creator__profile").get(pk=o.pk)
        is_init = _is_initiator(o, request.user)
        to = None
        if action in ("accept", "decline") and o.status == Offer.PENDING and not is_init:
            to = Offer.ACCEPTED if action == "accept" else Offer.DECLINED
        elif action == "withdraw" and o.status == Offer.PENDING and is_init:
            to = Offer.WITHDRAWN
        elif action == "complete" and o.status == Offer.ACCEPTED:
            to = Offer.COMPLETED
        if to is None:
            messages.error(request, "That isn't available for this offer right now.")
        else:
            o.status, o.responded_at = to, timezone.now()
            o.save()
            if to == Offer.COMPLETED:
                for person in (o.brand.profile, o.creator.profile):
                    person.deals_done += 1
                    person.save()
            messages.success(request, ACTION_MESSAGES[action])
    return redirect("offer", pk=pk)


@login_required
@require_POST
@throttle("review", limit=20, window=3600)
def review_add(request, pk):
    o = _offer_or_404(request, pk)
    if o.status != Offer.COMPLETED:
        messages.error(request, "You can leave a review once the work is marked as finished.")
        return redirect("offer", pk=pk)
    subject = o.creator if request.user.pk == o.brand_id else o.brand
    form = ReviewForm(request.POST)
    if form.is_valid():
        Review.objects.update_or_create(author=request.user, subject=subject, defaults={
            "offer": o, "rating": form.cleaned_data["rating"], "comment": form.cleaned_data["comment"].strip()})
        refresh_rating(subject)
        messages.success(request, "Review posted. Honesty looks good on you.")
    else:
        messages.error(request, next(iter(form.errors.values()))[0])
    return redirect(reverse("offer", args=[pk]) + "#review")


@login_required
@require_POST
@throttle("msg", limit=60, window=3600)
def message_send(request, pk):
    live = request.headers.get("X-Kyto") == "chat"  # sent from the chat box without a page reload
    o = _offer_or_404(request, pk)
    body = request.POST.get("body", "").strip()[:1000]
    if not o.is_open:
        if live:
            return JsonResponse({"ok": False, "error": "This chat is closed, so no new messages."}, status=409)
        messages.error(request, "This offer is closed, so new messages can't be sent.")
    elif body:
        m = Message.objects.create(offer=o, sender=request.user, body=body)
        o.save(update_fields=["updated"])
        if live:
            return JsonResponse({"ok": True, "id": m.pk})
    elif live:
        return JsonResponse({"ok": False, "error": "Type a message first."}, status=400)
    return redirect(reverse("offer", args=[pk]) + "#end")


@never_cache
@login_required
def inbox(request):
    u = request.user
    f = request.GET.get("s", "")
    qs = Offer.objects.filter(Q(brand=u) | Q(creator=u)).select_related("brand__profile", "creator__profile")
    if f == "pending":
        qs = qs.filter(status=Offer.PENDING)
    elif f == "active":
        qs = qs.filter(status=Offer.ACCEPTED)
    elif f == "closed":
        qs = qs.filter(status__in=[Offer.DECLINED, Offer.WITHDRAWN, Offer.COMPLETED])
    else:
        f = ""
    offers = list(qs[:100])
    unread = dict(Message.objects.filter(offer__in=offers, read=False).exclude(sender=u)
                  .values_list("offer").annotate(c=Count("id")))
    last = {}
    for m in Message.objects.filter(offer__in=offers).order_by("created").values("offer_id", "body", "sender_id"):
        last[m["offer_id"]] = ("You: " if m["sender_id"] == u.pk else "") + m["body"]
    items = [(o, (o.creator if o.brand_id == u.pk else o.brand).profile, unread.get(o.pk, 0), last.get(o.pk) or o.message)
             for o in offers]
    return render(request, "core/inbox.html", {"items": items, "f": f})


def robots(request):
    body = ("User-agent: *\nDisallow: /inbox/\nDisallow: /offers/\nDisallow: /hire/\nDisallow: /settings/\n"
            "Disallow: /go/\nDisallow: /reset/\nDisallow: /api/\nAllow: /\n")
    return HttpResponse(body, content_type="text/plain")


def about(request):
    return render(request, "core/about.html")


def humans(request):
    body = (f"/* THE TEAM */\nBuilt by: Zyrac\nInstagram: {settings.ZYRAC_URL}\nFrom: Ahmedabad, Gujarat, India\n\n"
            f"/* THE SITE */\nName: {settings.SITE_NAME}\nMade with: Django, vanilla JavaScript and hand-written CSS\n")
    return HttpResponse(body, content_type="text/plain; charset=utf-8")


# ---------- verification, shop photos, media ----------
@login_required
@require_POST
def verify_request(request):
    p = request.user.profile
    if p.verified:
        messages.info(request, "You're already verified.")
    elif p.verify_requested:
        messages.info(request, "Your request is already with us. We'll review it soon.")
    elif p.is_brand and not (p.address and p.photos.exists()):
        messages.error(request, "Add your shop address and at least one shop photo first, so we have something to check.")
    elif not p.is_brand and not (p.followers and p.showcase.exists()):
        messages.error(request, "Add your follower count and at least one reel first, so we have something to check.")
    else:
        Profile.objects.filter(pk=p.pk).update(verify_requested=True)
        messages.success(request, "Request sent. We'll check your profile and add the verified tick.")
    return redirect(reverse("settings") + "#verify")


@login_required
@require_POST
@throttle("photo", limit=20, window=3600)
def photo_add(request):
    p = request.user.profile
    if not p.is_brand:
        return redirect("settings")
    if p.photos.count() >= 6:
        messages.error(request, "You can add up to 6 photos. Remove one to add another.")
        return redirect(reverse("settings") + "#shop")
    form = PhotoForm(request.POST, request.FILES)
    if form.is_valid():
        content = form.cleaned_data["image"]
        photo = ShopPhoto(profile=p)
        photo.image.save(content.name, content, save=True)
        p.save()
        messages.success(request, "Photo added to your shop page.")
    else:
        messages.error(request, next(iter(form.errors.values()))[0])
    return redirect(reverse("settings") + "#shop")


@login_required
@require_POST
def photo_remove(request, pk):
    p = request.user.profile
    get_object_or_404(ShopPhoto, pk=pk, profile=p).delete()
    p.save()
    messages.success(request, "Photo removed.")
    return redirect(reverse("settings") + "#shop")


def media_file(request, path):
    """Serves uploaded shop photos. Only .jpg files inside MEDIA_ROOT, never anything else."""
    from django.core.exceptions import SuspiciousFileOperation
    from django.utils._os import safe_join
    if not path.endswith(".jpg"):
        raise Http404
    try:
        full = safe_join(settings.MEDIA_ROOT, path)
    except SuspiciousFileOperation:
        raise Http404
    if not os.path.isfile(full):
        raise Http404
    resp = FileResponse(open(full, "rb"), content_type="image/jpeg")
    resp["Cache-Control"] = "public, max-age=86400"
    resp["X-Content-Type-Options"] = "nosniff"
    return resp


def unread_count(request):
    """Tiny JSON endpoint the page asks every few seconds so the inbox badge updates by itself."""
    if not request.user.is_authenticated:
        return JsonResponse({"count": 0}, status=401)
    resp = JsonResponse({"count": inbox_total(request.user)})
    resp["Cache-Control"] = "no-store"
    return resp
