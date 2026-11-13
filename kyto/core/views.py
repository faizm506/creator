import logging
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
from django.utils.html import escape
from django.utils.formats import date_format
from django.utils.http import url_has_allowed_host_and_scheme
from django.views.decorators.cache import never_cache
from django.views.decorators.http import require_POST

from .context import inbox_total

from .forms import (BoostForm, CampaignForm, OfferForm, PhotoForm, ProfileForm, ProposalForm, ReportForm,
                    ReviewForm, ShowcaseForm, SignupForm, TermsForm)
from .models import (NICHES, RANK_ORDER, BoostRequest, Campaign, Kudos, Message, Offer, PlusInterest, Profile, Report,
                     Review, ShopPhoto, ShowcasePost, refresh_rating, waiting_for)
from .utils import client_ip, hit, qr_svg, throttle, upi_link


def not_found(request, exception):
    return render(request, "core/404.html", status=404)


def _creators():
    return Profile.objects.filter(role=Profile.CREATOR).select_related("user")


sec_log = logging.getLogger("kyto.security")
app_log = logging.getLogger("kyto.app")


def _back(request, default):
    ref = request.META.get("HTTP_REFERER", "")
    ok = ref and url_has_allowed_host_and_scheme(ref, allowed_hosts={request.get_host()})
    return ref if ok else default


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
    if not request.user.is_authenticated:
        return redirect("login")
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
    me = request.user.profile
    ids = [it["p"].id for it in items if it["kind"] in ("creator", "brand")]
    kudosed = set(Kudos.objects.filter(user=request.user, profile_id__in=ids).values_list("profile_id", flat=True))
    return render(request, "core/home.html", {
        "feed": feed, "items": items, "stories": stories, "niches": [n for n in NICHES if n[0] != "other"],
        "rail_creators": creators[:5], "rail_brands": brands[:3], "kudosed": kudosed,
        "me": me, "my_info": rank_info(me), "level": me.level_info(),
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

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["username"].label = "Instagram handle"
        form.fields["username"].widget.attrs.update(autocapitalize="none", autocorrect="off", spellcheck="false",
                                                    autocomplete="username", autofocus=True)
        form.fields["password"].widget.attrs.update(autocomplete="current-password")
        return form

    def post(self, request, *args, **kwargs):
        if "username" in request.POST:  # people type @Handle or capitals: that's fine
            data = request.POST.copy()
            data["username"] = data["username"].strip().lstrip("@").lower()
            request.POST = data
        ip_key, user_key = self._keys()
        if cache.get(ip_key, 0) >= 15 or cache.get(user_key, 0) >= 8:
            sec_log.warning("login_lockout ip=%s key=%s", ip_key, user_key)
            messages.error(request, "Too many wrong tries. For your safety, wait 15 minutes or reset your password.")
            return redirect("login")
        return super().post(request, *args, **kwargs)

    def form_invalid(self, form):
        sec_log.info("login_failed ip=%s key=%s", *self._keys())
        for k in self._keys():
            hit(k, 900)
        return super().form_invalid(form)

    def form_valid(self, form):
        cache.delete(self._keys()[1])
        resp = super().form_valid(form)
        if not self.request.POST.get("remember"):
            self.request.session.set_expiry(0)  # signed out when the browser closes
        return resp


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
    if p.best_streak >= 7:
        b.append(f"{p.best_streak}-day streak")
    if p.kudos >= 10:
        b.append("Kudos magnet")
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
        "level": p.level_info(), "i_kudosed": Kudos.objects.filter(user=request.user, profile=p).exists(),
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
    msgs = list(o.messages.all())
    thread = [{"id": 0, "mine": is_init, "body": o.message, "day": _day_label(o.created), "time": _clock(o.created),
               "read": True, "heart": False, "first": True}]
    thread += [{"id": m.pk, "mine": m.sender_id == request.user.pk, "body": m.body, "day": _day_label(m.created),
                "time": _clock(m.created), "read": m.read, "heart": m.heart, "first": False} for m in msgs]
    return render(request, "core/offer.html", {
        "o": o, "thread": thread, "is_brand": is_brand, "is_init": is_init, "other": other,
        "last_id": msgs[-1].pk if msgs else 0, "items": _inbox_items(request.user), "current": o.pk,
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


def _day_label(dt):
    d, today = timezone.localtime(dt).date(), timezone.localdate()
    if d == today:
        return "Today"
    if d == today - timedelta(days=1):
        return "Yesterday"
    return date_format(d, "j F")


def _clock(dt):
    return date_format(timezone.localtime(dt), "g:i a")


@login_required
@require_POST
@throttle("msg", limit=120, window=600)
def message_send(request, pk):
    live = request.headers.get("X-Kyto") == "chat"  # sent from the chat box without a page reload
    o = _offer_or_404(request, pk)
    body = request.POST.get("body", "").strip()[:1000]
    cid = re.sub(r"[^A-Za-z0-9-]", "", request.POST.get("cid", ""))[:36]
    if not o.is_open:
        if live:
            return JsonResponse({"ok": False, "error": "This chat is closed, so no new messages."}, status=409)
        messages.error(request, "This offer is closed, so new messages can't be sent.")
    elif body:
        m = Message.objects.filter(offer=o, sender=request.user, client_id=cid).first() if cid else None
        if m is None:  # a retry with the same cid finds the first copy instead of posting again
            try:
                m = Message.objects.create(offer=o, sender=request.user, body=body, client_id=cid)
            except IntegrityError:
                m = Message.objects.get(sender=request.user, client_id=cid)
            Offer.objects.filter(pk=o.pk).update(updated=timezone.now())
        if live:
            return JsonResponse({"ok": True, "id": m.pk, "time": _clock(m.created), "day": _day_label(m.created)})
    elif live:
        return JsonResponse({"ok": False, "error": "Type a message first."}, status=400)
    return redirect(reverse("offer", args=[pk]) + "#end")


@never_cache
@login_required
def offer_poll(request, pk):
    """Small, cheap answer the open chat asks every few seconds: new messages, who has read what, typing."""
    me = request.user
    if hit(f"poll:{me.pk}", 60) > 90:  # at most 90 checks a minute per person
        return JsonResponse({"ok": False, "error": "slow down"}, status=429)
    o = _offer_or_404(request, pk)
    try:
        after = max(0, int(request.GET.get("after", 0)))
    except ValueError:
        after = 0
    other_id = o.creator_id if me.pk == o.brand_id else o.brand_id
    recent = list(o.messages.order_by("-id")[:60])[::-1]
    if any(not m.read and m.sender_id != me.pk for m in recent):
        o.messages.filter(read=False).exclude(sender=me).update(read=True)
    new = [m for m in recent if m.id > after]
    return JsonResponse({
        "ok": True, "status": o.status, "last": recent[-1].id if recent else 0, "since": recent[0].id if recent else 0,
        "messages": [{"id": m.id, "mine": m.sender_id == me.pk, "body": m.body, "time": _clock(m.created),
                      "day": _day_label(m.created), "read": m.read or m.sender_id != me.pk, "heart": m.heart} for m in new],
        "read": [m.id for m in recent if m.sender_id == me.pk and m.read],
        "hearts": [m.id for m in recent if m.heart],
        "typing": cache.get(f"typing:{o.pk}:{other_id}") is not None,
    })


@login_required
@require_POST
@throttle("typing", limit=400, window=600)
def offer_typing(request, pk):
    o = _offer_or_404(request, pk)
    cache.set(f"typing:{o.pk}:{request.user.pk}", 1, 6)
    return JsonResponse({"ok": True})


@login_required
@require_POST
@throttle("heart", limit=300, window=600)
def message_heart(request, pk, mid):
    o = _offer_or_404(request, pk)
    m = get_object_or_404(Message, pk=mid, offer=o)
    if m.sender_id == request.user.pk:
        return JsonResponse({"ok": False, "error": "You can only heart messages you receive."}, status=400)
    m.heart = not m.heart
    m.save(update_fields=["heart"])
    return JsonResponse({"ok": True, "heart": m.heart})


def _inbox_items(user, f=""):
    """Chats for the list: (offer, the other person, unread count, preview text)."""
    qs = Offer.objects.filter(Q(brand=user) | Q(creator=user)).select_related("brand__profile", "creator__profile")
    if f == "pending":
        qs = qs.filter(status=Offer.PENDING)
    elif f == "active":
        qs = qs.filter(status=Offer.ACCEPTED)
    elif f == "closed":
        qs = qs.filter(status__in=[Offer.DECLINED, Offer.WITHDRAWN, Offer.COMPLETED])
    offers = list(qs[:100])
    unread = dict(Message.objects.filter(offer__in=offers, read=False).exclude(sender=user)
                  .values_list("offer").annotate(c=Count("id")))
    last = {}
    for m in Message.objects.filter(offer__in=offers).order_by("id").values("offer_id", "body", "sender_id"):
        last[m["offer_id"]] = ("You: " if m["sender_id"] == user.pk else "") + m["body"]
    return [(o, (o.creator if o.brand_id == user.pk else o.brand).profile, unread.get(o.pk, 0), last.get(o.pk) or o.message)
            for o in offers]


@never_cache
@login_required
def inbox(request):
    f = request.GET.get("s", "")
    f = f if f in ("pending", "active", "closed") else ""
    cur = request.GET.get("cur", "")
    ctx = {"items": _inbox_items(request.user, f), "f": f, "current": int(cur) if cur.isdigit() else 0}
    if request.GET.get("partial"):  # only the rows, for the live refresh
        return render(request, "core/_threads.html", ctx)
    return render(request, "core/inbox.html", ctx)


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


# ---------- consent, legal pages ----------
@login_required
def accept_terms(request):
    nxt = request.GET.get("next") or request.POST.get("next") or "/"
    if not url_has_allowed_host_and_scheme(nxt, allowed_hosts={request.get_host()}):
        nxt = "/"
    form = TermsForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        Profile.objects.filter(pk=request.user.profile.pk).update(
            terms_version=settings.TERMS_VERSION, terms_accepted_at=timezone.now(), adult_confirmed=True)
        request.session["terms_v"] = settings.TERMS_VERSION
        messages.success(request, "Thanks! You're all set.")
        return redirect(nxt)
    return render(request, "core/accept_terms.html", {"form": form, "next": nxt})


def terms(request):
    return render(request, "core/terms.html")


def privacy(request):
    return render(request, "core/privacy.html")


def guidelines(request):
    return render(request, "core/guidelines.html")


def grievance(request):
    return render(request, "core/grievance.html")


# ---------- fun: streak, kudos ----------
@login_required
@require_POST
def checkin(request):
    p = request.user.profile
    before = p.checkin_xp
    if p.check_in():
        p.save()
        n = p.streak
        line = ("Day 1. Every legend starts somewhere (usually in pyjamas)." if n == 1 else
                "3 days in a row! Your mom would be proud." if n == 3 else
                "A whole week! Sharma ji's son is taking notes." if n == 7 else
                f"Day {n}. Your kite is flying high.")
        messages.success(request, f"{line} +{p.checkin_xp - before} XP")
    else:
        messages.info(request, "Already flown your kite today. Come back tomorrow, don't be greedy.")
    return redirect(_back(request, reverse("home")))


@login_required
@require_POST
@throttle("kudos", limit=120, window=3600)
def kudos_toggle(request, handle):
    target = get_object_or_404(Profile, handle=handle.lower())
    live = request.headers.get("X-Kyto") in ("chat", "json")
    if target.user_id == request.user.pk:
        if live:
            return JsonResponse({"ok": False, "error": "You can't give yourself kudos. Nice try though."}, status=400)
        messages.info(request, "You can't give yourself kudos. Nice try though.")
        return redirect(_back(request, reverse("home")))
    obj, created = Kudos.objects.get_or_create(user=request.user, profile=target)
    if not created:
        obj.delete()
    count = Kudos.objects.filter(profile=target).count()
    Profile.objects.filter(pk=target.pk).update(kudos=count)
    if live:
        return JsonResponse({"ok": True, "on": created, "count": count})
    return redirect(_back(request, reverse("creator", args=[target.handle])))


# ---------- safety: report, export my data ----------
@login_required
@throttle("report", limit=10, window=86400)
def report(request, kind, pk):
    review = offer = None
    if kind == "profile":
        profile = get_object_or_404(Profile, pk=pk)
        if profile.user_id == request.user.pk:
            raise Http404
        label, back = f"@{profile.handle}", reverse("creator", args=[profile.handle])
    elif kind == "review":
        review = get_object_or_404(Review.objects.select_related("author__profile"), pk=pk)
        profile = review.author.profile
        if profile.user_id == request.user.pk:
            raise Http404
        label, back = f"a review by @{profile.handle}", _back(request, reverse("home"))
    elif kind == "offer":
        offer = _offer_or_404(request, pk)
        profile = (offer.creator if request.user.pk == offer.brand_id else offer.brand).profile
        label, back = f"this chat with @{profile.handle}", reverse("offer", args=[offer.pk])
    else:
        raise Http404
    form = ReportForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        Report.objects.create(reporter=request.user, profile=profile, review=review, offer=offer,
                              reason=form.cleaned_data["reason"], details=form.cleaned_data["details"].strip())
        sec_log.info("report_created reporter=%s about=%s reason=%s", request.user.pk, profile.pk, form.cleaned_data["reason"])
        messages.success(request, "Report sent. A real person will look at it, usually within a day. Thank you for keeping Kyto clean.")
        return redirect(back)
    return render(request, "core/report.html", {"form": form, "label": label, "back": back})


@never_cache
@login_required
def export_data(request):
    """Everything we hold about you, as a file (your right to access your data)."""
    u, p = request.user, request.user.profile
    offers = Offer.objects.filter(Q(brand=u) | Q(creator=u)).select_related("brand__profile", "creator__profile")
    data = {
        "exported_at": timezone.now().isoformat(),
        "account": {"username": u.username, "email": u.email, "joined": u.date_joined.isoformat()},
        "profile": {
            "role": p.role, "name": p.display_name, "handle": p.handle, "niche": p.niche, "city": p.city,
            "address": p.address, "about": p.bio, "followers": p.followers, "engagement_percent": float(p.engagement),
            "price_per_post": p.rate_per_post, "whatsapp": p.whatsapp, "show_whatsapp_to_members": p.show_contact,
            "score": p.rank_score, "verified": p.verified, "kudos": p.kudos, "streak": p.streak,
            "accepted_terms_version": p.terms_version,
            "accepted_terms_at": p.terms_accepted_at.isoformat() if p.terms_accepted_at else None,
        },
        "reels": [s.url for s in p.showcase.all()],
        "offers": [{
            "title": o.title, "budget": o.budget, "status": o.status, "started_by": o.initiator,
            "brand": o.brand.profile.handle, "creator": o.creator.profile.handle, "message": o.message,
            "created": o.created.isoformat(),
            "chat": [{"from": m.sender.profile.handle, "text": m.body, "at": m.created.isoformat()}
                     for m in o.messages.select_related("sender__profile")],
        } for o in offers],
        "reviews_written": [{"about": r.subject.profile.handle, "rating": r.rating, "comment": r.comment}
                            for r in Review.objects.filter(author=u).select_related("subject__profile")],
        "reviews_received": [{"from": r.author.profile.handle, "rating": r.rating, "comment": r.comment}
                             for r in Review.objects.filter(subject=u).select_related("author__profile")],
        "kudos_given_to": list(Kudos.objects.filter(user=u).values_list("profile__handle", flat=True)),
    }
    resp = JsonResponse(data, json_dumps_params={"indent": 2, "ensure_ascii": False})
    resp["Content-Disposition"] = 'attachment; filename="kyto-my-data.json"'
    return resp


# ---------- Kyto Plus: coming-soon page and waiting list (nothing is sold) ----------
@login_required
def plus(request):
    return render(request, "core/plus.html", {"interested": PlusInterest.objects.filter(user=request.user).exists()})


@login_required
@require_POST
def plus_toggle(request):
    obj, created = PlusInterest.objects.get_or_create(user=request.user)
    if created:
        messages.success(request, "You're on the list. We'll tell you before anything changes, and nothing is charged.")
    else:
        obj.delete()
        messages.info(request, "Removed from the list. No hard feelings.")
    return redirect("plus")


# ---------- monitoring and error pages ----------
def healthz(request):
    """Is the app running? Cheap, no database. Point an uptime monitor here."""
    resp = JsonResponse({"status": "ok"})
    resp["Cache-Control"] = "no-store"
    return resp


def readyz(request):
    """Can the app do its job? Checks the database and the cache. 503 when something is down."""
    checks = {}
    try:
        Profile.objects.only("id").first()
        checks["database"] = "ok"
    except Exception:
        checks["database"] = "fail"
        app_log.exception("readyz database check failed")
    try:
        cache.set("readyz", 1, 5)
        checks["cache"] = "ok" if cache.get("readyz") == 1 else "fail"
    except Exception:
        checks["cache"] = "fail"
        app_log.exception("readyz cache check failed")
    ok = all(c == "ok" for c in checks.values())
    resp = JsonResponse({"status": "ok" if ok else "degraded", "checks": checks, "version": settings.APP_VERSION},
                        status=200 if ok else 503)
    resp["Cache-Control"] = "no-store"
    return resp


_ERROR_PAGE = """<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{title}</title></head><body style="font-family:-apple-system,Segoe UI,sans-serif;text-align:center;padding:12vh 20px">
<h1>{title}</h1><p>{body}</p><p><a href="/">Back to home</a></p>{ref}</body></html>"""


def server_error(request, template_name="500.html"):
    rid = escape(getattr(request, "request_id", "-"))
    return HttpResponse(_ERROR_PAGE.format(
        title="Something went wrong on our side.", body="We've been notified. Please try again in a minute.",
        ref=f"<p>Reference: <code>{rid}</code><br>Quote this if you contact us.</p>"), status=500)


def csrf_failure(request, reason=""):
    sec_log.warning("csrf_failure path=%s reason=%s", request.path, reason)
    return HttpResponse(_ERROR_PAGE.format(
        title="Your session expired.", body="For your safety this page timed out. Go back, refresh it and try again.", ref=""), status=403)
