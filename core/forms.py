import re

from django import forms
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django.db import transaction

from .models import Application, BoostRequest, Campaign, Profile, ShowcasePost

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
        self.fields["username"].help_text = "Without @. Lowercase letters, numbers, dots, underscores."
        self.fields["username"].widget.attrs.update(autocapitalize="none", autocomplete="username")
        self.fields["email"].widget.attrs["autocomplete"] = "email"

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
        widgets = {"bio": forms.Textarea(attrs={"rows": 3, "maxlength": 280})}

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
        widgets = {"description": forms.Textarea(attrs={"rows": 5})}


class ApplicationForm(forms.ModelForm):
    class Meta:
        model = Application
        fields = ["message"]
        widgets = {"message": forms.Textarea(attrs={"rows": 3, "placeholder": "Why you're a good fit, in a few lines."})}


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
