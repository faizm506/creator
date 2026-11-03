import math
from datetime import timedelta

from django.conf import settings
from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.contrib.auth.decorators import login_required
from django.core.paginator import Paginator
from django.db import IntegrityError
from django.db.models import F, Q, Sum
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import ApplicationForm, BoostForm, CampaignForm, ProfileForm, ShowcaseForm, SignupForm
from .models import NICHES, RANK_ORDER, Application, BoostRequest, Campaign, Profile, ShowcasePost
from .utils import client_ip, hit, qr_svg, throttle, upi_link


def not_found(request, exception):
    return render(request, "core/404.html", status=404)


def _creators():
    return Profile.objects.filter(role=Profile.CREATOR).select_related("user")


def featured_shelf(request, limit=4, **filters):
    """Boosted creators, rotated fairly: whoever has been shown least goes first.
    Needs a bio, niche and followers so paid spots never show empty pages."""
    qs = (_creators().filter(boost_until__gt=timezone.now(), followers__gt=0, **filters)
          .exclude(bio="").exclude(niche="").order_by("boost_impressions", *RANK_ORDER))
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


def home(request):
    top = list(_creators().order_by(*RANK_ORDER)[:5])
    rising = _creators().filter(created__gte=timezone.now() - timedelta(days=30), rank_score__gte=30).order_by(*RANK_ORDER)[:4]
    stats = {
        "creators": _creators().count(),
        "brands": Profile.objects.filter(role=Profile.BRAND).count(),
        "campaigns": Campaign.objects.filter(is_open=True).count(),
        "reach": _creators().aggregate(s=Sum("followers"))["s"] or 0,
    }
    return render(request, "core/home.html", {"top": top, "rising": rising, "featured": featured_shelf(request, 4),
        "champions": niche_champions(), "niches": NICHES, "stats": stats})


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
    """Caps sign-in attempts at 12 per IP every 15 minutes (slows password guessing)."""
    template_name = "registration/login.html"
    redirect_authenticated_user = True

    def post(self, request, *args, **kwargs):
        if hit(f"login-check:{client_ip(request)}", 900) > 12:
            messages.error(request, "Too many sign-in attempts. Try again in 15 minutes.")
            return redirect("login")
        return super().post(request, *args, **kwargs)


def leaderboard(request):
    niche = request.GET.get("niche", "")
    city = request.GET.get("city", "").strip()[:60]
    q = request.GET.get("q", "").strip()[:60]
    qs = _creators()
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
    featured = featured_shelf(request, 3, **fl) if page.number == 1 and not q else []
    params = request.GET.copy()
    params.pop("page", None)
    return render(request, "core/leaderboard.html", {
        "page": page, "featured": featured, "niches": NICHES, "niche": niche, "city": city, "q": q,
        "qs": params.urlencode(),
    })


def rank_info(p):
    """Rank among all creators, in the creator's city and niche, with the same tie-breaks as the leaderboard."""
    base = _creators()
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
        b.append("Verified creator")
    if info["overall"] <= 10:
        b.append("Top 10 overall")
    if p.city and info["city"] and info["city"] <= 10:
        b.append(f"#{info['city']} in {p.city}")
    if p.niche and info["niche"] and info["niche"] <= 3:
        b.append(f"Top 3 in {p.get_niche_display()}")
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
    info = rank_info(p) if p.is_creator else None
    similar = []
    if p.is_creator and p.niche:
        similar = _creators().filter(niche=p.niche).exclude(pk=p.pk).order_by(*RANK_ORDER)[:3]
    return render(request, "core/creator.html", {
        "p": p, "info": info, "badges": earned_badges(p, info) if info else [],
        "showcase": p.showcase.all(), "similar": similar, "is_owner": is_owner,
        "can_contact": request.user.is_authenticated and p.show_contact and bool(p.whatsapp),
        "rate": p.suggested_rate if p.is_creator else None,
    })


def ig_go(request, handle):
    """Counts a visit, then sends the person to the creator's Instagram (fixed destination, no open redirect)."""
    p = get_object_or_404(Profile, handle=handle.lower())
    if hit(f"igclick:{client_ip(request)}:{p.pk}", 3600) == 1:
        Profile.objects.filter(pk=p.pk).update(ig_clicks=F("ig_clicks") + 1)
    return HttpResponseRedirect(f"https://www.instagram.com/{p.handle}/")


@login_required
def settings_view(request):
    profile = request.user.profile
    form = ProfileForm(request.POST or None, instance=profile)
    if request.method == "POST" and form.is_valid():
        form.save()
        messages.success(request, "Profile saved.")
        return redirect("settings")
    info = rank_info(profile) if profile.is_creator else None
    pending = request.user.boost_requests.filter(status=BoostRequest.PENDING).exists()
    return render(request, "core/settings.html", {
        "form": form, "p": profile, "info": info, "pending": pending,
        "steps": profile.next_steps if profile.is_creator else [],
        "showcase": profile.showcase.all(), "showcase_form": ShowcaseForm(),
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
        messages.success(request, "Added to your showcase." if made else "That one is already in your showcase.")
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
    qs = Campaign.objects.filter(is_open=True).select_related("brand__profile")
    niche = request.GET.get("niche", "")
    if niche in dict(NICHES):
        qs = qs.filter(niche=niche)
    else:
        niche = ""
    page = Paginator(qs, 12).get_page(request.GET.get("page"))
    return render(request, "core/campaigns.html", {"page": page, "niches": NICHES, "niche": niche})


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
        messages.success(request, "Campaign posted.")
        return redirect("campaign", pk=c.pk)
    return render(request, "core/campaign_form.html", {"form": form})


def campaign_detail(request, pk):
    c = get_object_or_404(Campaign.objects.select_related("brand__profile"), pk=pk)
    is_owner = request.user.is_authenticated and c.brand_id == request.user.id
    applications = c.applications.select_related("creator__profile") if is_owner else []
    applied = request.user.is_authenticated and c.applications.filter(creator=request.user).exists()
    can_apply = (request.user.is_authenticated and request.user.profile.role == Profile.CREATOR
                 and c.is_open and not applied)
    return render(request, "core/campaign.html", {
        "c": c, "is_owner": is_owner, "applications": applications, "applied": applied,
        "can_apply": can_apply, "form": ApplicationForm(),
    })


@login_required
@require_POST
@throttle("apply", limit=20, window=3600)
def campaign_apply(request, pk):
    c = get_object_or_404(Campaign, pk=pk, is_open=True)
    if request.user.profile.role != Profile.CREATOR:
        messages.error(request, "Only creator accounts can apply.")
        return redirect("campaign", pk=pk)
    form = ApplicationForm(request.POST)
    if form.is_valid():
        a = form.save(commit=False)
        a.campaign, a.creator = c, request.user
        try:
            a.save()
            messages.success(request, "Application sent.")
        except IntegrityError:
            messages.info(request, "You have already applied.")
    else:
        messages.error(request, "Add a short message with your application.")
    return redirect("campaign", pk=pk)


@login_required
@require_POST
def campaign_close(request, pk):
    c = get_object_or_404(Campaign, pk=pk, brand=request.user)
    c.is_open = False
    c.save(update_fields=["is_open"])
    messages.success(request, "Campaign closed.")
    return redirect("campaign", pk=pk)
