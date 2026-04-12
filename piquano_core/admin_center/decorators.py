"""
View-Decorators fuer Piquano-Berechtigungen und Feature-Toggles.

Usage:
    @require_permission("crm.deals.write")
    def deal_edit(request, pk): ...

    @require_feature("crm", "briefings")
    def briefing_list(request): ...
"""

from __future__ import annotations

from functools import wraps

from django.conf import settings
from django.http import HttpResponseForbidden
from django.shortcuts import redirect


def require_permission(codename: str):
    """Decorator: require a specific Piquano permission."""

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                login_url = getattr(settings, "LOGIN_URL", "/accounts/login/")
                return redirect(f"{login_url}?next={request.path}")
            if not request.user.has_piquano_perm(codename):
                return HttpResponseForbidden("Keine Berechtigung")
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def require_feature(app_label: str, module_name: str):
    """Decorator: require a feature toggle to be enabled."""

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                login_url = getattr(settings, "LOGIN_URL", "/accounts/login/")
                return redirect(f"{login_url}?next={request.path}")
            if not request.user.is_feature_enabled(app_label, module_name):
                return HttpResponseForbidden("Feature nicht verfuegbar")
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator
