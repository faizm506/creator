from django import template

register = template.Library()


@register.filter
def compact(n):
    """12800 -> 12.8K, 1200000 -> 1.2M"""
    try:
        n = int(n)
    except (TypeError, ValueError):
        return n
    for size, suffix in ((1_000_000, "M"), (1_000, "K")):
        if n >= size:
            v = n / size
            return f"{v:.1f}".rstrip("0").rstrip(".") + suffix
    return str(n)


@register.filter
def rupees(n):
    try:
        return "₹{:,}".format(int(n))
    except (TypeError, ValueError):
        return ""


@register.filter
def mask_email(e):
    try:
        name, domain = e.split("@", 1)
    except (AttributeError, ValueError):
        return ""
    return f"{name[:1]}{'•' * max(2, min(6, len(name) - 1))}@{domain}"


@register.filter
def chips(value):
    """'2 reels + 3 stories, 1 post' -> ['2 reels', '3 stories', '1 post']"""
    import re
    return [p.strip() for p in re.split(r"\s*(?:\+|,|&|\band\b)\s*", value or "") if p.strip()][:6]


@register.filter
def stars(value):
    """4.6 -> '★★★★★' (rounded), 3 -> '★★★☆☆'"""
    try:
        n = max(0, min(5, int(round(float(value)))))
    except (TypeError, ValueError):
        n = 0
    return "★" * n + "☆" * (5 - n)
