from django.conf import settings
from django.db.models import Q

from .models import Message, Offer


def site(request):
    ctx = {"SITE_NAME": settings.SITE_NAME, "TAGLINE": settings.TAGLINE, "ZYRAC_URL": settings.ZYRAC_URL, "BOOST_ENABLED": settings.BOOST_ENABLED,
           "SUPPORT_WHATSAPP": settings.SUPPORT_WHATSAPP}
    u = getattr(request, "user", None)
    if u is not None and u.is_authenticated:
        unread = Message.objects.filter(read=False).filter(Q(offer__brand=u) | Q(offer__creator=u)).exclude(sender=u).count()
        waiting = Offer.objects.filter(creator=u, status=Offer.PENDING).count()
        ctx["inbox_count"] = unread + waiting
    return ctx
