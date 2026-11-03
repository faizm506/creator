import math

from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.utils import timezone

NICHES = [
    ("fashion", "Fashion"), ("beauty", "Beauty"), ("food", "Food"), ("travel", "Travel"),
    ("fitness", "Fitness"), ("tech", "Tech"), ("lifestyle", "Lifestyle"), ("comedy", "Comedy"),
    ("education", "Education"), ("gaming", "Gaming"), ("business", "Business"), ("other", "Other"),
]

RANK_ORDER = ("-rank_score", "-followers", "created")  # score, then audience, then who joined first

handle_validator = RegexValidator(r"^[a-z0-9._]{2,30}$", "Use 2–30 lowercase letters, numbers, dots or underscores.")
phone_validator = RegexValidator(r"^\+?\d{10,14}$", "Enter digits only, with country code, e.g. 919876543210.")


class Profile(models.Model):
    CREATOR, BRAND = "creator", "brand"
    ROLES = [(CREATOR, "Creator"), (BRAND, "Brand")]

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile")
    role = models.CharField(max_length=10, choices=ROLES, default=CREATOR)
    handle = models.CharField(max_length=30, unique=True, validators=[handle_validator])
    display_name = models.CharField(max_length=60)
    niche = models.CharField(max_length=20, choices=NICHES, blank=True)
    city = models.CharField(max_length=60, blank=True)
    bio = models.CharField(max_length=280, blank=True)
    followers = models.PositiveIntegerField(default=0, validators=[MaxValueValidator(500_000_000)])
    engagement = models.DecimalField(
        "Engagement rate (%)", max_digits=4, decimal_places=2, default=0,
        validators=[MinValueValidator(0), MaxValueValidator(50)],
    )
    rate_per_post = models.PositiveIntegerField("Rate per post (₹)", null=True, blank=True, validators=[MaxValueValidator(100_000_000)])
    whatsapp = models.CharField(max_length=15, blank=True, validators=[phone_validator])
    show_contact = models.BooleanField("Show my WhatsApp to signed-in members", default=False)
    verified = models.BooleanField(default=False)
    boost_until = models.DateTimeField(null=True, blank=True)
    views = models.PositiveIntegerField(default=0, editable=False)
    ig_clicks = models.PositiveIntegerField(default=0, editable=False)
    boost_impressions = models.PositiveIntegerField(default=0, editable=False)
    rank_score = models.FloatField(default=0, db_index=True, editable=False)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = list(RANK_ORDER)

    def __str__(self):
        return f"@{self.handle}"

    @property
    def is_creator(self):
        return self.role == self.CREATOR

    @property
    def is_boosted(self):
        return bool(self.boost_until and self.boost_until > timezone.now())

    @property
    def avatar_class(self):
        return f"av-{sum(ord(c) for c in self.handle) % 12}"

    @property
    def initial(self):
        return (self.display_name or self.handle)[:1].upper()

    @property
    def completeness(self):
        checks = [bool(self.display_name), bool(self.bio), bool(self.niche), bool(self.city),
                  self.followers > 0, float(self.engagement) > 0, bool(self.rate_per_post)]
        return int(100 * sum(checks) / len(checks))

    def score_parts(self):
        """(label, points, max). Sums to at most 100. Boost never changes it."""
        n = min(3, self.showcase.count()) if self.pk else 0
        return [
            ("Profile completeness", self.completeness * 0.25, 25),
            ("Audience size", min(35.0, math.log10(self.followers + 1) * 5.25), 35),
            ("Engagement rate", min(25.0, float(self.engagement) * 4), 25),
            ("Reel showcase", n * 10 / 3, 10),
            ("Verified", 5 if self.verified else 0, 5),
        ]

    def compute_score(self):
        return round(sum(v for _, v, _ in self.score_parts()), 1)

    @property
    def engaged_per_post(self):
        return int(self.followers * float(self.engagement) / 100)

    @property
    def suggested_rate(self):
        """Rough fair price per post in INR, from audience and engagement. An estimate only."""
        if self.followers < 1000:
            return None
        k = self.followers / 1000
        factor = max(0.6, min(1.6, float(self.engagement) / 3)) if self.engagement else 0.8
        step = 500 if k * 80 * factor >= 5000 else 100
        r = lambda x: int(round(x / step) * step)
        return r(k * 80 * factor), r(k * 200 * factor)

    @property
    def next_steps(self):
        """Missing items worth points, biggest first."""
        per = round(25 / 7, 1)
        n = self.showcase.count() if self.pk else 0
        items = [
            ("Add a short bio", bool(self.bio), per), ("Choose your niche", bool(self.niche), per),
            ("Add your city", bool(self.city), per), ("Add your follower count", self.followers > 0, per),
            ("Add your engagement rate", float(self.engagement) > 0, per),
            ("Add your rate per post", bool(self.rate_per_post), per),
            ("Add a reel to your showcase", n >= 1, 3.3), ("Add a second reel", n >= 2, 3.3),
            ("Add a third reel", n >= 3, 3.4), ("Ask us for the verified tick", self.verified, 5.0),
        ]
        todo = [(t, pts) for t, done, pts in items if not done]
        return sorted(todo, key=lambda x: -x[1])[:4]

    def save(self, *args, **kwargs):
        self.handle = self.handle.lower()
        self.rank_score = self.compute_score()
        super().save(*args, **kwargs)


class ShowcasePost(models.Model):
    """A public Instagram reel/post a creator highlights. Only the shortcode is stored."""
    KINDS = [("reel", "Reel"), ("p", "Post"), ("tv", "Video")]
    profile = models.ForeignKey(Profile, on_delete=models.CASCADE, related_name="showcase")
    code = models.CharField(max_length=20, validators=[RegexValidator(r"^[A-Za-z0-9_-]{5,20}$")])
    kind = models.CharField(max_length=5, choices=KINDS, default="reel")
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created"]
        constraints = [models.UniqueConstraint(fields=["profile", "code"], name="unique_showcase_per_profile")]

    @property
    def url(self):
        return f"https://www.instagram.com/{self.kind}/{self.code}/"

    @property
    def embed_url(self):
        return self.url + "embed/"


class Campaign(models.Model):
    brand = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="campaigns")
    title = models.CharField(max_length=100)
    description = models.TextField(max_length=1500)
    niche = models.CharField(max_length=20, choices=NICHES, blank=True)
    city = models.CharField(max_length=60, blank=True)
    budget = models.PositiveIntegerField("Budget (₹)", validators=[MaxValueValidator(100_000_000)])
    deliverables = models.CharField(max_length=200, help_text="e.g. 2 reels + 3 stories")
    is_open = models.BooleanField(default=True)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created"]

    def __str__(self):
        return self.title


class Application(models.Model):
    campaign = models.ForeignKey(Campaign, on_delete=models.CASCADE, related_name="applications")
    creator = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="applications")
    message = models.CharField(max_length=500)
    created = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created"]
        constraints = [models.UniqueConstraint(fields=["campaign", "creator"], name="one_application_per_campaign")]


class BoostRequest(models.Model):
    PENDING, APPROVED, REJECTED = "pending", "approved", "rejected"
    STATUSES = [(PENDING, "Pending"), (APPROVED, "Approved"), (REJECTED, "Rejected")]

    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="boost_requests")
    plan = models.CharField(max_length=4)
    amount = models.PositiveIntegerField()
    days = models.PositiveIntegerField()
    utr = models.CharField("UPI reference (UTR)", max_length=12, unique=True,
                           validators=[RegexValidator(r"^\d{12}$", "The UPI reference is exactly 12 digits.")])
    status = models.CharField(max_length=10, choices=STATUSES, default=PENDING, db_index=True)
    created = models.DateTimeField(auto_now_add=True)
    reviewed_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created"]

    def __str__(self):
        return f"{self.user} · ₹{self.amount} · {self.status}"


# Staff/superusers created from the command line get a profile automatically
# so the site never errors for them. Normal signups create theirs in SignupForm.
import re as _re

from django.db.models.signals import post_save
from django.dispatch import receiver


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def ensure_staff_profile(sender, instance, created, **kwargs):
    if created and instance.is_staff and not hasattr(instance, "profile"):
        handle = _re.sub(r"[^a-z0-9._]", "", instance.username.lower())[:30] or f"user{instance.pk}"
        if len(handle) < 2 or Profile.objects.filter(handle=handle).exists():
            handle = f"{handle}{instance.pk}"[:30]
        Profile.objects.create(user=instance, handle=handle, display_name=instance.username[:60])
