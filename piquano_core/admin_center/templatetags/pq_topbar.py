from django import template

register = template.Library()


@register.simple_tag
def user_initials(user):
    """Return consistent 2-letter initials: first_name[0] + last_name[0]."""
    first = (getattr(user, "first_name", "") or getattr(user, "email", "?"))[0].upper()
    last_name = getattr(user, "last_name", "") or ""
    last = last_name[0].upper() if last_name else ""
    return f"{first}{last}"
