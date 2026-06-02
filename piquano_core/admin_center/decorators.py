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
from django.contrib import messages
from django.shortcuts import redirect
from django.http import JsonResponse


def _is_api_request(request):
    """Detect API/AJAX requests that expect JSON responses."""
    if request.content_type == "application/json":
        return True
    accept = request.META.get("HTTP_ACCEPT", "")
    if "application/json" in accept and "text/html" not in accept:
        return True
    return request.headers.get("X-Requested-With") == "XMLHttpRequest"


def require_permission(codename: str):
    """Decorator: require a specific Piquano permission."""

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                if _is_api_request(request):
                    return JsonResponse({"error": "Nicht angemeldet."}, status=401)
                login_url = getattr(settings, "LOGIN_URL", "/accounts/login/")
                return redirect(f"{login_url}?next={request.path}")
            if not hasattr(request.user, "has_piquano_perm"):
                return view_func(request, *args, **kwargs)  # Middleware fehlt → fail-open
            if not request.user.has_piquano_perm(codename):
                if _is_api_request(request):
                    return JsonResponse({"error": "Keine Berechtigung."}, status=403)
                messages.error(request, "Du hast keinen Zugriff auf diese Funktion.")
                referer = request.META.get("HTTP_REFERER", "/")
                return redirect(referer)
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator


def require_feature(app_label: str, module_name: str):
    """Decorator: require a feature toggle to be enabled."""

    def decorator(view_func):
        @wraps(view_func)
        def wrapper(request, *args, **kwargs):
            if not request.user.is_authenticated:
                if _is_api_request(request):
                    return JsonResponse({"error": "Nicht angemeldet."}, status=401)
                login_url = getattr(settings, "LOGIN_URL", "/accounts/login/")
                return redirect(f"{login_url}?next={request.path}")
            if not hasattr(request.user, "is_feature_enabled"):
                return view_func(request, *args, **kwargs)  # Middleware fehlt → fail-open
            if not request.user.is_feature_enabled(app_label, module_name):
                if _is_api_request(request):
                    return JsonResponse({"error": "Feature nicht verfuegbar."}, status=403)
                messages.error(request, "Diese Funktion ist nicht freigeschaltet.")
                referer = request.META.get("HTTP_REFERER", "/")
                return redirect(referer)
            return view_func(request, *args, **kwargs)

        return wrapper

    return decorator
