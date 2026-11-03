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
