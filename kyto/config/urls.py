from django.conf import settings
from django.contrib import admin
from django.urls import include, path

handler404 = "core.views.not_found"
handler500 = "core.views.server_error"

urlpatterns = [
    path(settings.ADMIN_URL, admin.site.urls),
    path("", include("core.urls")),
]
