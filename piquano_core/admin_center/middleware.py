"""
PiquanoPermissionMiddleware: Loads permissions and feature toggles onto request.user.

Lazy-loading: DB wird erst beim ersten Aufruf von has_piquano_perm / is_feature_enabled
abgefragt. Ergebnisse werden fuer die Dauer des Requests gecached.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from django.http import HttpRequest, HttpResponse


def _load_perms(user):
    """Load all granted permissions for user into a set of codename strings.

    Merges user-level and team-level permissions. Team permissions are
    loaded if the user has a ``team_id`` attribute (set by the consumer app).
    """
    if user._piquano_perms is None:
        from .models import TeamPermission, UserPermission

        # User-level permissions
        user_qs = (
            UserPermission.objects.filter(user=user, is_granted=True)
            .select_related("permission")
            .values_list(
                "permission__app_label",
                "permission__module_name",
                "permission__codename",
            )
        )
        perms = {f"{app}.{module}.{code}" for app, module, code in user_qs}

        # Team-level permissions (if user belongs to a team)
        team_id = getattr(user, "team_id", None)
        if team_id:
            team_qs = (
                TeamPermission.objects.filter(team_id=team_id, is_granted=True)
                .select_related("permission")
                .values_list(
                    "permission__app_label",
                    "permission__module_name",
                    "permission__codename",
                )
            )
            perms |= {f"{app}.{module}.{code}" for app, module, code in team_qs}

        user._piquano_perms = perms
    return user._piquano_perms


def _load_toggles(user):
    """Load all feature toggles into a dict {(app, module): is_enabled}."""
    if user._piquano_toggles is None:
        from .models import FeatureToggle

        qs = FeatureToggle.objects.values_list("app_label", "module_name", "is_enabled")
        user._piquano_toggles = {(app, module): enabled for app, module, enabled in qs}
    return user._piquano_toggles


def _check_perm(user, codename: str) -> bool:
    """Check if user has a specific permission.

    codename format: "app.module.action" e.g. "crm.deals.write"
    Superusers, staff users, and Authelia admins always have all permissions.
    """
    if user.is_superuser or user.is_staff or getattr(user, "_piquano_is_admin", False):
        return True
    perms = _load_perms(user)
    return codename in perms


def _check_toggle(user, app_label: str, module_name: str) -> bool:
    """Check if a feature is enabled."""
    toggles = _load_toggles(user)
    return toggles.get((app_label, module_name), True)


class PiquanoPermissionMiddleware:
    """Loads permissions and feature toggles onto request.user (lazy)."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request: HttpRequest) -> HttpResponse:
        if hasattr(request, "user") and request.user.is_authenticated:
            # Read Authelia admin group directly from header — survives
            # enrich_from_crm overwriting is_staff.
            from django.conf import settings

            admin_group = getattr(settings, "PIQUANO_AUTH_ADMIN_GROUP", "admins")
            groups_raw = request.META.get("HTTP_REMOTE_GROUPS", "")
            groups = {g.strip() for g in groups_raw.split(",") if g.strip()}
            request.user._piquano_is_admin = admin_group in groups

            request.user._piquano_perms = None
            request.user._piquano_toggles = None
            request.user.has_piquano_perm = lambda codename: _check_perm(request.user, codename)
            request.user.is_feature_enabled = lambda app, module: _check_toggle(
                request.user, app, module
            )
        return self.get_response(request)
