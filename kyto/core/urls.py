from django.contrib.auth import views as auth_views
from django.contrib.messages.views import SuccessMessageMixin
from django.urls import reverse_lazy
from django.urls import path

from . import views
from .utils import throttle


class PasswordChange(SuccessMessageMixin, auth_views.PasswordChangeView):
    template_name = "registration/password_change.html"
    success_url = reverse_lazy("settings")
    success_message = "Password updated. Your other devices were signed out."


urlpatterns = [
    path("", views.home, name="home"),
    path("about/", views.about, name="about"),
    path("how-it-works/", views.how, name="how"),
    path("signup/", views.signup, name="signup"),
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("leaderboard/", views.leaderboard, name="leaderboard"),
    path("u/<str:handle>/", views.creator_detail, name="creator"),
    path("go/<str:handle>/", views.ig_go, name="go"),
    path("settings/", views.settings_view, name="settings"),
    path("forgot-password/", throttle("reset", 6, 3600)(auth_views.PasswordResetView.as_view(
        template_name="registration/reset_form.html", email_template_name="registration/reset_email.txt",
        subject_template_name="registration/reset_subject.txt", success_url=reverse_lazy("password_reset_done"))),
        name="password_reset"),
    path("forgot-password/sent/", auth_views.PasswordResetDoneView.as_view(template_name="registration/reset_done.html"),
         name="password_reset_done"),
    path("reset/done/", auth_views.PasswordResetCompleteView.as_view(template_name="registration/reset_complete.html"),
         name="password_reset_complete"),
    path("reset/<uidb64>/<token>/", auth_views.PasswordResetConfirmView.as_view(
        template_name="registration/reset_confirm.html", success_url=reverse_lazy("password_reset_complete")),
        name="password_reset_confirm"),
    path("api/unread/", views.unread_count, name="unread_count"),
    path("robots.txt", views.robots, name="robots"),
    path("humans.txt", views.humans, name="humans"),
    path("accept-terms/", views.accept_terms, name="accept_terms"),
    path("terms/", views.terms, name="terms"),
    path("privacy/", views.privacy, name="privacy"),
    path("guidelines/", views.guidelines, name="guidelines"),
    path("grievance/", views.grievance, name="grievance"),
    path("checkin/", views.checkin, name="checkin"),
    path("kudos/<str:handle>/", views.kudos_toggle, name="kudos"),
    path("report/<str:kind>/<int:pk>/", views.report, name="report"),
    path("account/export/", views.export_data, name="export_data"),
    path("plus/", views.plus, name="plus"),
    path("plus/toggle/", views.plus_toggle, name="plus_toggle"),
    path("password/", throttle("pwd", 8)(PasswordChange.as_view()), name="password"),
    path("security/sign-out-others/", views.logout_others, name="logout_others"),
    path("account/delete/", views.delete_account, name="delete_account"),
    path("inbox/", views.inbox, name="inbox"),
    path("hire/<str:handle>/", views.offer_new, name="offer_new"),
    path("offers/<int:pk>/", views.offer_detail, name="offer"),
    path("offers/<int:pk>/message/", views.message_send, name="message_send"),
    path("offers/<int:pk>/poll/", views.offer_poll, name="offer_poll"),
    path("offers/<int:pk>/typing/", views.offer_typing, name="offer_typing"),
    path("offers/<int:pk>/heart/<int:mid>/", views.message_heart, name="message_heart"),
    path("offers/<int:pk>/review/", views.review_add, name="review_add"),
    path("offers/<int:pk>/<str:action>/", views.offer_action, name="offer_action"),
    path("media/<path:path>", views.media_file, name="media"),
    path("verify/request/", views.verify_request, name="verify_request"),
    path("photos/add/", views.photo_add, name="photo_add"),
    path("photos/<int:pk>/remove/", views.photo_remove, name="photo_remove"),
    path("showcase/add/", views.showcase_add, name="showcase_add"),
    path("showcase/<int:pk>/remove/", views.showcase_remove, name="showcase_remove"),
    path("boost/", views.boost, name="boost"),
    path("campaigns/", views.campaign_list, name="campaigns"),
    path("campaigns/new/", views.campaign_new, name="campaign_new"),
    path("campaigns/<int:pk>/", views.campaign_detail, name="campaign"),
    path("campaigns/<int:pk>/apply/", views.campaign_apply, name="campaign_apply"),
    path("campaigns/<int:pk>/close/", views.campaign_close, name="campaign_close"),
]
