import re
import time

from django import forms
from django.conf import settings
from django.core import signing
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.db import transaction
from django.utils import timezone

from .utils import process_image

from .models import Offer, Application, BoostRequest, Campaign, Profile, Report, ShowcasePost

User = get_user_model()


class SignupForm(UserCreationForm):
    email = forms.EmailField()
    display_name = forms.CharField(max_length=60, label="Name")
    role = forms.ChoiceField(choices=Profile.ROLES, widget=forms.RadioSelect, initial=Profile.CREATOR, label="I am a")
    adult = forms.BooleanField(required=True, error_messages={"required": "Please confirm that you are 18 or older."})
    agree = forms.BooleanField(required=True, error_messages={"required": "Please agree to the Terms and Privacy Policy to join."})
    website = forms.CharField(required=False, widget=forms.TextInput(attrs={"tabindex": "-1", "autocomplete": "off"}))  # bot trap
    ts = forms.CharField(required=False, widget=forms.HiddenInput)  # signed time the form was shown

    class Meta:
        model = User
        fields = ("username", "email")

    field_order = ["role", "display_name", "username", "email", "password1", "password2", "adult", "agree", "website", "ts"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["username"].label = "Instagram handle"
        self.fields["username"].help_text = "Your Instagram username, without the @."
        self.fields["username"].widget.attrs.update(autocapitalize="none", autocomplete="username")
        self.fields["email"].widget.attrs["autocomplete"] = "email"
        self.fields["ts"].initial = signing.dumps(int(time.time()))
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

    def clean(self):
        data = super().clean()
        if data.get("website"):
            raise forms.ValidationError("Something went wrong. Please try again.")
        try:
            shown = signing.loads(data.get("ts") or "", max_age=7200)
        except signing.BadSignature:
            raise forms.ValidationError("This form expired. Please try again.")
        if time.time() - shown < 3:
            raise forms.ValidationError("That was very quick! Please check your details and press the button again.")
        return data

    @transaction.atomic
    def save(self, commit=True):
        user = super().save(commit=False)
        user.email = self.cleaned_data["email"]
        user.username = self.cleaned_data["username"]
        user.save()
        Profile.objects.create(
            user=user, handle=user.username, role=self.cleaned_data["role"],
            display_name=self.cleaned_data["display_name"],
            terms_version=settings.TERMS_VERSION, terms_accepted_at=timezone.now(), adult_confirmed=True,
        )
        return user


class ProfileForm(forms.ModelForm):
    class Meta:
        model = Profile
        fields = ["display_name", "niche", "city", "address", "bio", "followers", "engagement",
                  "rate_per_post", "whatsapp", "show_contact"]
        widgets = {"bio": forms.Textarea(attrs={"rows": 3, "maxlength": 280, "placeholder": "Tell brands what you create and who follows you."})}
        labels = {"display_name": "Your name", "bio": "About you", "city": "City", "address": "Shop address", "niche": "What do you post about?",
                  "followers": "Instagram followers", "rate_per_post": "Your price per post (₹)",
                  "whatsapp": "WhatsApp number", "show_contact": "Let any signed-in member see my WhatsApp"}
        help_texts = {
            "address": "Full address so creators can find you on the map. Only add it if people can visit.",
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
            self.fields["display_name"].label = "Brand name"
            self.fields["bio"].label = "About your shop"
            self.fields["bio"].widget.attrs["placeholder"] = "What do you sell, and what makes your shop special?"
            self.fields["niche"].label = "Type of business"
            self.fields["niche"].help_text = "Helps creators in that niche find you."
        else:
            del self.fields["address"]
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

    def __init__(self, *args, brand=None, by_creator=False, **kwargs):
        super().__init__(*args, **kwargs)
        if by_creator:
            self.fields["budget"].label = "Your price (₹)"
            self.fields["message"].widget.attrs["placeholder"] = "Say hello, and share why you're a good fit."
        self.fields["campaign"].queryset = Campaign.objects.filter(brand=brand, is_open=True)
        self.fields["campaign"].required = False
        self.fields["campaign"].empty_label = "Not linked to a campaign"
        self.fields["campaign"].label = "Campaign (optional)"

    def clean_budget(self):
        b = self.cleaned_data["budget"]
        if b < 500:
            raise forms.ValidationError("Offers start at ₹500.")
        return b


class ProposalForm(forms.ModelForm):
    """A creator's proposal on a campaign: their own price and a short message."""
    class Meta:
        model = Offer
        fields = ["budget", "message"]
        labels = {"budget": "Your price (₹)", "message": "Your message to the brand"}
        help_texts = {"budget": "What you'd like to be paid for this work."}
        widgets = {"message": forms.Textarea(attrs={"rows": 4, "maxlength": 1000,
                   "placeholder": "Say hello, share why you're a good fit, and mention a reel you're proud of."})}

    def clean_budget(self):
        b = self.cleaned_data["budget"]
        if b < 500:
            raise forms.ValidationError("Proposals start at ₹500.")
        return b


class ReviewForm(forms.Form):
    rating = forms.TypedChoiceField(choices=[(i, str(i)) for i in range(5, 0, -1)], coerce=int,
                                    error_messages={"required": "Tap a star to rate.", "invalid_choice": "Tap a star to rate."})
    comment = forms.CharField(max_length=400, required=False, label="Tell others how it went",
                              widget=forms.Textarea(attrs={"rows": 3, "maxlength": 400, "placeholder": "Was it easy to work together? Optional."}))


class PhotoForm(forms.Form):
    image = forms.FileField(label="Shop photo")

    def clean_image(self):
        return process_image(self.cleaned_data["image"])


class ReportForm(forms.Form):
    reason = forms.ChoiceField(choices=Report.REASONS, widget=forms.RadioSelect,
                               error_messages={"required": "Please choose what is wrong."})
    details = forms.CharField(max_length=500, required=False, label="Anything else we should know?",
                              widget=forms.Textarea(attrs={"rows": 3, "maxlength": 500, "placeholder": "Optional. A few words help us act faster."}))


class TermsForm(forms.Form):
    adult = forms.BooleanField(required=True, error_messages={"required": "Please confirm that you are 18 or older."})
    agree = forms.BooleanField(required=True, error_messages={"required": "Please agree to continue."})
