import io
from functools import wraps
from urllib.parse import quote

import qrcode
import qrcode.image.svg
from django.conf import settings
from django.contrib import messages
from django.core.cache import cache
from django.shortcuts import redirect
from django.utils.http import url_has_allowed_host_and_scheme
from django.utils.safestring import mark_safe


def client_ip(request):
    """Real visitor IP. X-Forwarded-For is only trusted when TRUSTED_PROXY_COUNT says a proxy really sits in front."""
    n = settings.TRUSTED_PROXY_COUNT
    if n:
        parts = [p.strip() for p in request.META.get("HTTP_X_FORWARDED_FOR", "").split(",") if p.strip()]
        if len(parts) >= n:
            return parts[-n]
    return request.META.get("REMOTE_ADDR", "unknown")


def hit(key, window):
    """Increment a counter that expires after `window` seconds; returns the new count."""
    cache.add(key, 0, window)
    try:
        return cache.incr(key)
    except ValueError:
        cache.set(key, 1, window)
        return 1


def throttle(name, limit, window=900):
    """Limit POST requests per IP (and per user when signed in)."""
    def deco(view):
        @wraps(view)
        def wrapper(request, *args, **kwargs):
            if request.method == "POST":
                who = request.user.pk if request.user.is_authenticated else client_ip(request)
                if hit(f"thr:{name}:{who}", window) > limit:
                    messages.error(request, "Too many attempts. Please wait a few minutes and try again.")
                    ref = request.META.get("HTTP_REFERER", "")
                    ok = ref and url_has_allowed_host_and_scheme(ref, allowed_hosts={request.get_host()})
                    return redirect(ref if ok else "/")
            return view(request, *args, **kwargs)
        return wrapper
    return deco


def upi_link(amount, note):
    return (f"upi://pay?pa={quote(settings.UPI_ID)}&pn={quote(settings.UPI_NAME)}"
            f"&am={amount}&cu=INR&tn={quote(note)}")


def qr_svg(data):
    img = qrcode.make(data, image_factory=qrcode.image.svg.SvgPathImage, box_size=10, border=1)
    buf = io.BytesIO()
    img.save(buf)
    return mark_safe(buf.getvalue().decode())


MAX_UPLOAD = 4 * 1024 * 1024


def process_image(f, max_side=1400):
    """Validate an uploaded photo and re-encode it as a clean JPEG (strips metadata and any hidden payload)."""
    from io import BytesIO
    from uuid import uuid4

    from django.core.exceptions import ValidationError
    from django.core.files.base import ContentFile
    from PIL import Image, ImageOps

    Image.MAX_IMAGE_PIXELS = 30_000_000
    if f.size > MAX_UPLOAD:
        raise ValidationError("That photo is too big. Please use one under 4 MB.")
    try:
        img = Image.open(f)
        img.verify()
        f.seek(0)
        img = ImageOps.exif_transpose(Image.open(f)).convert("RGB")
    except Exception:
        raise ValidationError("We couldn't read that file as a photo. Try a JPG or PNG.")
    img.thumbnail((max_side, max_side))
    buf = BytesIO()
    img.save(buf, "JPEG", quality=82, optimize=True)
    return ContentFile(buf.getvalue(), name=f"{uuid4().hex}.jpg")
