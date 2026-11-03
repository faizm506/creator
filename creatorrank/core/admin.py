from datetime import timedelta

from django.contrib import admin, messages
from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import Application, BoostRequest, Campaign, Profile, ShowcasePost


@admin.register(Profile)
class ProfileAdmin(admin.ModelAdmin):
    list_display = ("handle", "role", "niche", "city", "followers", "rank_score", "verified", "boost_until", "boost_impressions")
    list_filter = ("role", "verified", "niche")
    search_fields = ("handle", "display_name", "user__email")
    list_editable = ("verified",)
    readonly_fields = ("rank_score",)


@admin.register(BoostRequest)
class BoostRequestAdmin(admin.ModelAdmin):
    list_display = ("created", "user", "amount", "days", "utr", "status")
    list_filter = ("status",)
    search_fields = ("utr", "user__username")
    readonly_fields = ("user", "plan", "amount", "days", "utr", "created", "reviewed_at")
    actions = ["approve", "reject"]

    @admin.action(description="Approve selected (payment received) and start boost")
    def approve(self, request, queryset):
        done, skipped = 0, []
        with transaction.atomic():
            for br in queryset.select_for_update().filter(status=BoostRequest.PENDING):
                p = br.user.profile
                if not p.is_boosted and Profile.objects.filter(
                        role=Profile.CREATOR, niche=p.niche, boost_until__gt=timezone.now()
                ).count() >= settings.FEATURED_SLOTS_PER_NICHE:
                    skipped.append(p.handle)
                    continue
                start = max(timezone.now(), p.boost_until or timezone.now())
                p.boost_until = start + timedelta(days=br.days)
                p.save()
                br.status, br.reviewed_at = BoostRequest.APPROVED, timezone.now()
                br.save()
                done += 1
        self.message_user(request, f"{done} boost(s) approved.", messages.SUCCESS)
        if skipped:
            self.message_user(request, "Niche is full, left pending (refund by UPI or approve later): " + ", ".join(skipped), messages.WARNING)

    @admin.action(description="Reject selected (payment not found)")
    def reject(self, request, queryset):
        n = queryset.filter(status=BoostRequest.PENDING).update(status=BoostRequest.REJECTED, reviewed_at=timezone.now())
        self.message_user(request, f"{n} request(s) rejected.", messages.WARNING)


admin.site.register(Campaign)
admin.site.register(Application)


@admin.register(ShowcasePost)
class ShowcaseAdmin(admin.ModelAdmin):
    list_display = ("profile", "kind", "code", "created")
    search_fields = ("profile__handle", "code")
