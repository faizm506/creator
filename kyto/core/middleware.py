from django.conf import settings

CSP = (
    "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; font-src 'self'; "
    "connect-src 'self'; frame-src https://www.instagram.com; object-src 'none'; base-uri 'self'; "
    "form-action 'self'; frame-ancestors 'none'"
)


class SecurityHeaders:
    """Adds a strict Content-Security-Policy (not on the admin, which needs inline styles) and a Permissions-Policy."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        resp = self.get_response(request)
        resp.headers.setdefault("Permissions-Policy", "camera=(), microphone=(), geolocation=(), payment=(), usb=()")
        in_admin = request.path.startswith("/" + settings.ADMIN_URL)
        debug_page = settings.DEBUG and resp.status_code in (404, 500)  # Django's debug pages use inline styles
        if not in_admin and not debug_page:
            resp.headers.setdefault("Content-Security-Policy", CSP)
        return resp
