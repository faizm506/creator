import re
import uuid
from urllib.parse import quote

from django.conf import settings
from django.http import JsonResponse
from django.shortcuts import redirect
from django.urls import reverse

from .logging_utils import request_id_var

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; "
    "connect-src 'self'; frame-src https://www.instagram.com https://www.google.com; object-src 'none'; base-uri 'self'; "
    "form-action 'self'; frame-ancestors 'none'"
)


class SecurityHeaders:
    """Adds a strict Content-Security-Policy (not on the admin, which needs inline styles) and a Permissions-Policy."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        resp = self.get_response(request)
        resp.headers.setdefault("X-Frame-Options", "DENY")  # redirects from the login wall never reach Django's own middleware for this
        resp.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=(), usb=()")
        in_admin = request.path.startswith("/" + settings.ADMIN_URL)
        debug_page = settings.DEBUG and resp.status_code in (404, 500)  # Django's debug pages use inline styles
        if not in_admin and not debug_page:
            resp.headers.setdefault("Content-Security-Policy", CSP)
        resp.headers.setdefault("Cross-Origin-Resource-Policy", "same-origin")
        user = getattr(request, "user", None)
        if user is not None and user.is_authenticated and "text/html" in resp.get("Content-Type", ""):
            resp.headers.setdefault("Cache-Control", "private, no-cache")  # pages for signed-in people are never shared caches
        return resp


PUBLIC = ("/healthz/", "/readyz/", "/login/", "/signup/", "/forgot-password/", "/reset/", "/about/", "/how-it-works/", "/privacy/", "/terms/",
          "/guidelines/", "/grievance/", "/robots.txt", "/humans.txt", "/static/", "/.well-known/")
TERMS_EXEMPT = ("/healthz/", "/readyz/", "/accept-terms/", "/logout/", "/privacy/", "/terms/", "/guidelines/", "/grievance/", "/about/",
                "/how-it-works/", "/account/delete/", "/account/export/", "/static/", "/robots.txt", "/humans.txt", "/api/")


class LoginRequired:
    """Like Instagram: you have to sign in to look around. Only the sign-in pages, About and the legal pages are public.
    Signed-in people must also have accepted the current Terms and Privacy Policy (and confirmed they are 18+)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        path = request.path
        if path.startswith("/" + settings.ADMIN_URL):
            return self.get_response(request)
        if not request.user.is_authenticated:
            if path.startswith(PUBLIC):
                return self.get_response(request)
            if path.startswith("/api/"):
                return JsonResponse({"detail": "Please sign in."}, status=401)
            nxt = "" if path == "/" else "?next=" + quote(request.get_full_path())
            return redirect(reverse("login") + nxt)
        if not path.startswith(TERMS_EXEMPT) and request.session.get("terms_v") != settings.TERMS_VERSION:
            profile = getattr(request.user, "profile", None)
            if profile is None or profile.terms_version == settings.TERMS_VERSION:
                request.session["terms_v"] = settings.TERMS_VERSION
            else:
                return redirect(reverse("accept_terms") + "?next=" + quote(request.get_full_path()))
        return self.get_response(request)


class RequestId:
    """Gives every request a short reference (also sent back as X-Request-ID) that shows up in the logs and on error pages."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        rid = re.sub(r"[^A-Za-z0-9-]", "", request.META.get("HTTP_X_REQUEST_ID", ""))[:40] or uuid.uuid4().hex[:12]
        request.request_id = rid
        token = request_id_var.set(rid)
        try:
            resp = self.get_response(request)
        finally:
            request_id_var.reset(token)
        resp.headers["X-Request-ID"] = rid
        return resp
