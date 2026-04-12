"""
Template Tags fuer Piquano-Berechtigungen.

Usage:
    {% load piquano_perms %}
    {% has_perm "crm.deals.write" as can_edit_deals %}
    {% if can_edit_deals %}...{% endif %}

    {% feature_enabled "crm" "briefings" as briefings_on %}
    {% if briefings_on %}...{% endif %}
"""

from __future__ import annotations

from django import template

register = template.Library()


@register.simple_tag(takes_context=True)
def has_perm(context, codename: str) -> bool:
    """Check if the current user has a Piquano permission."""
    request = context.get("request")
    if (
        request
        and hasattr(request, "user")
        and request.user.is_authenticated
        and hasattr(request.user, "has_piquano_perm")
    ):
        return request.user.has_piquano_perm(codename)
    return False


@register.simple_tag(takes_context=True)
def feature_enabled(context, app_label: str, module_name: str) -> bool:
    """Check if a feature toggle is enabled."""
    request = context.get("request")
    if (
        request
        and hasattr(request, "user")
        and request.user.is_authenticated
        and hasattr(request.user, "is_feature_enabled")
    ):
        return request.user.is_feature_enabled(app_label, module_name)
    return True  # default: enabled if not configured
