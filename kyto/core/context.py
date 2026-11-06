from django.conf import settings
from django.db.models import Q

from .models import Message, waiting_for


def inbox_total(u):
    """Unread messages plus offers waiting for this person's answer."""
    unread = Message.objects.filter(read=False).filter(Q(offer__brand=u) | Q(offer__creator=u)).exclude(sender=u).count()
    return unread + waiting_for(u).count()


def site(request):
    ctx = {"SITE_NAME": settings.SITE_NAME, "TAGLINE": settings.TAGLINE, "ZYRAC_URL": settings.ZYRAC_URL,
           "BOOST_ENABLED": settings.BOOST_ENABLED, "SUPPORT_WHATSAPP": settings.SUPPORT_WHATSAPP,
           "ADMIN_PATH": "/" + settings.ADMIN_URL}
    u = getattr(request, "user", None)
    if u is not None and u.is_authenticated:
        ctx["inbox_count"] = inbox_total(u)
    return ctx
