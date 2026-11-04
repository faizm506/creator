import re

from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.db import transaction

from .models import Offer, Application, BoostRequest, Campaign, Profile, ShowcasePost

User = get_user_model()


class SignupForm(UserCreationForm):
    email = forms.EmailField()
    display_name = forms.CharField(max_length=60, label="Name")
    role = forms.ChoiceField(choices=Profile.ROLES, widget=forms.RadioSelect, initial=Profile.CREATOR, label="I am a")

    class Meta:
        model = User
        fields = ("username", "email")

    field_order = ["role", "display_name", "username", "email", "password1", "password2"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Instagram handle"
        self.fields["username"].help_text = "Your Instagram username, without the @."
        self.fields["username"].widget.attrs.update(autocapitalize="none", autocomplete="username")
        self.fields["email"].widget.attrs["autocomplete"] = "email"
        self.fields["role"].label = "I'm joining as"
        self.fields["display_name"].label = "Your name"
        self.fields["display_name"].widget.attrs["autocomplete"] = "name"
        self.fields["email"].help_text = "Used only to recover your account. We never show it."
        self.fields["password1"].help_text = "At least 10 characters. Avoid common passwords."
        self.fields["password2"].help_text = "Type the same password again."
        for n in ("password1", "password2"):
            self.fields[n].widget.attrs["autocomplete"] = "new-password"

    def clean_username(self):
        u = self.cleaned_data["username"].strip().lstrip("@").lower()
        if not re.fullmatch(r"[a-z0-9._]{2,30}", u):
            raise forms.ValidationError("Use 2–30 lowercase letters, numbers, dots or underscores.")
        if User.objects.filter(username__iexact=u).exists():
            raise forms.ValidationError("That handle is already registered.")
        return u

    def clean_email(self):
        e = self.cleaned_data["email"].strip().lower()
        if User.objects.filter(email__iexact=e).exists():
            raise forms.ValidationError("An account with this email already exists.")
        return e

    @transaction.atomic
    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.username = self.cleaned_data["username"]
        user.save()
        Profile.objects.create(
            user=user, handle=user.username, role=self.cleaned_data["role"],
            display_name=self.cleaned_data["display_name"],
        )
        return user


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ["display_name", "niche", "city", "bio", "followers", "engagement",
                  "rate_per_post", "whatsapp", "show_contact"]
        widgets = {"bio": forms.Textarea(attrs={"rows": 3, "maxlength": 280, "placeholder": "Tell brands what you create and who follows you."})}
        labels = {"display_name": "Your name", "bio": "About you", "city": "City", "niche": "What do you post about?",
                  "followers": "Instagram followers", "rate_per_post": "Your price per post (₹)",
                  "whatsapp": "WhatsApp number", "show_contact": "Let any signed-in member see my WhatsApp"}
        help_texts = {
            "city": "Used for city rankings. Type it the way brands search, like Ahmedabad.",
            "bio": "Up to 280 characters.",
            "followers": "Your current follower count on Instagram.",
            "engagement": "Average likes + comments per post, divided by followers, times 100. Most creators are between 1% and 6%.",
            "rate_per_post": "What you charge for one post. Leave blank if you're not sure yet.",
            "whatsapp": "Include the country code, like 919876543210. Numbers only.",
            "show_contact": "Off is safest. Your number is then shared only with a brand whose offer you accept.",
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance.role == Profile.BRAND:
            for f in ("followers", "engagement", "rate_per_post"):
                del self.fields[f]
        self.fields["niche"].required = False


class CampaignForm(forms.ModelForm):
    class Meta:
        model = Campaign
        fields = ["title", "description", "niche", "city", "budget", "deliverables"]
        widgets = {
            "description": forms.Textarea(attrs={"rows": 5, "placeholder": "Tell creators about your brand and what you want them to make."}),
            "title": forms.TextInput(attrs={"placeholder": "e.g. New cafe opening reels"}),
            "deliverables": forms.TextInput(attrs={"placeholder": "e.g. 2 reels + 3 stories"}),
            "city": forms.TextInput(attrs={"placeholder": "e.g. Ahmedabad"}),
        }
        labels = {"title": "What do you need?", "description": "Details", "niche": "Best for creators in",
                  "city": "City", "budget": "Your budget (₹)", "deliverables": "What should they deliver?"}
        help_texts = {"budget": "The total you can pay one creator.", "deliverables": "Use a plus between items.",
                      "niche": "Pick the closest match, or leave it open.", "city": "Leave blank if any city works."}


class ApplicationForm(forms.ModelForm):
    class Meta:
        model = Application
        fields = ["message"]
        widgets = {"message": forms.Textarea(attrs={"rows": 4, "placeholder": "Say hello, share why you're a good fit, and mention a past reel you're proud of."})}
        labels = {"message": "Your message to the brand"}


class BoostForm(forms.Form):
    plan = forms.ChoiceField(choices=[(k, v[0]) for k, v in settings.BOOST_PLANS.items()], widget=forms.RadioSelect)
    utr = forms.RegexField(
        r"^\d{12}$", label="UPI reference number (UTR)", max_length=12, min_length=12,
        error_messages={"invalid": "The UPI reference is exactly 12 digits. Find it in your payment receipt."},
    )

    def clean_utr(self):
        utr = self.cleaned_data["utr"]
        if BoostRequest.objects.filter(utr=utr).exists():
            raise forms.ValidationError("This reference number was already submitted.")
        return utr


_IG_RE = re.compile(
    r"^https?://(?:www\.)?instagram\.com/(?:([A-Za-z0-9._]+)/)?(reel|reels|p|tv)/([A-Za-z0-9_-]{5,20})/?(?:\?.*)?$"
)


class ShowcaseForm(forms.Form):
    url = forms.CharField(max_length=200, label="Instagram reel or post link")

    def __init__(self, *args, profile=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.profile = profile

    def clean_url(self):
        m = _IG_RE.match(self.cleaned_data["url"].strip())
        if not m:
            raise forms.ValidationError("Paste a public Instagram reel or post link, like instagram.com/reel/AbC123xyz/")
        owner, kind, code = m.groups()
        if owner and self.profile and owner.lower() != self.profile.handle:
            raise forms.ValidationError("That link belongs to a different account.")
        self.kind = "reel" if kind == "reels" else kind
        self.code = code
        return self.cleaned_data["url"]


class OfferForm(forms.ModelForm):
    class Meta:
        model = Offer
        fields = ["campaign", "title", "deliverables", "budget", "message"]
        widgets = {
            "message": forms.Textarea(attrs={"rows": 5, "maxlength": 1000, "placeholder": "Introduce your brand, what you need and when."}),
            "title": forms.TextInput(attrs={"placeholder": "e.g. Cafe launch reel"}),
            "deliverables": forms.TextInput(attrs={"placeholder": "e.g. 1 reel + 2 stories"}),
        }

    def __init__(self, *args, brand=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["campaign"].queryset = Campaign.objects.filter(brand=brand, is_open=True)
        self.fields["campaign"].required = False
        self.fields["campaign"].empty_label = "Not linked to a campaign"
        self.fields["campaign"].label = "Campaign (optional)"

    def clean_budget(self):
        b = self.cleaned_data["budget"]
        if b < 500:
            raise forms.ValidationError("Offers start at ₹500.")
        return b
