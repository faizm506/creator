from django.contrib.auth import views as auth_views
from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("how-it-works/", views.how, name="how"),
    path("signup/", views.signup, name="signup"),
    path("login/", views.LoginView.as_view(), name="login"),
    path("logout/", auth_views.LogoutView.as_view(), name="logout"),
    path("leaderboard/", views.leaderboard, name="leaderboard"),
    path("u/<str:handle>/", views.creator_detail, name="creator"),
    path("go/<str:handle>/", views.ig_go, name="go"),
    path("settings/", views.settings_view, name="settings"),
    path("showcase/add/", views.showcase_add, name="showcase_add"),
    path("showcase/<int:pk>/remove/", views.showcase_remove, name="showcase_remove"),
    path("boost/", views.boost, name="boost"),
    path("campaigns/", views.campaign_list, name="campaigns"),
    path("campaigns/new/", views.campaign_new, name="campaign_new"),
    path("campaigns/<int:pk>/", views.campaign_detail, name="campaign"),
    path("campaigns/<int:pk>/apply/", views.campaign_apply, name="campaign_apply"),
    path("campaigns/<int:pk>/close/", views.campaign_close, name="campaign_close"),
]
