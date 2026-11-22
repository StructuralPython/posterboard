from django import template
from django.utils import timezone

register = template.Library()


@register.filter
def until(value, now=None):
    """'in 3 days', 'in 5 hours', 'in 12 minutes', or 'due now'."""
    if not value:
        return ""
    seconds = (value - (now or timezone.now())).total_seconds()
    if seconds <= 60:
        return "due now"
    for size, unit in ((86400, "day"), (3600, "hour"), (60, "minute")):
        if seconds >= size:
            n = int(seconds // size)
            return f"in {n} {unit}{'s' if n != 1 else ''}"
    return "due now"


@register.filter
def percent_left(connection):
    """How much of the token's lifetime is left, 0 to 100 (for the meter)."""
    if not connection:
        return 0
    total = (connection.expires_at - connection.connected_at).total_seconds()
    left = connection.time_left().total_seconds()
    return max(0, min(100, round(100 * left / total))) if total > 0 else 0
