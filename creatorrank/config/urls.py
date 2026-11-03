from django.conf import settings
from django.contrib import admin
from django.urls import include, path

handler404 = "core.views.not_found"

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    path("", include("core.urls")),
]
