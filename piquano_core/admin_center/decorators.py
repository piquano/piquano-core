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
from django.shortcuts import redirect
from django.template import loader
from django.http import HttpResponseForbidden


def require_permission(codename: str):
    """Decorator: require a specific Piquano permission."""

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                login_url = getattr(settings, "LOGIN_URL", "/accounts/login/")
                return redirect(f"{login_url}?next={request.path}")
            if not hasattr(request.user, "has_piquano_perm"):
                return view_func(request, *args, **kwargs)  # Middleware fehlt → fail-open
            if not request.user.has_piquano_perm(codename):
                try:
                    template = loader.get_template("403.html")
                    return HttpResponseForbidden(template.render(request=request))
                except Exception:
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
            if not hasattr(request.user, "is_feature_enabled"):
                return view_func(request, *args, **kwargs)  # Middleware fehlt → fail-open
            if not request.user.is_feature_enabled(app_label, module_name):
                try:
                    template = loader.get_template("403.html")
                    return HttpResponseForbidden(template.render(request=request))
                except Exception:
                    return HttpResponseForbidden("Feature nicht verfuegbar")
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator
