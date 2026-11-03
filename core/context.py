from django.conf import settings


def site(request):
    return {"SITE_NAME": "CreatorRank", "SUPPORT_WHATSAPP": settings.SUPPORT_WHATSAPP}
