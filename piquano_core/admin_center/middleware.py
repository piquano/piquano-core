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
    """Load effective permissions for user into a set of codename strings.

    Logic: Team permissions as base, then user-level overrides.
    - Team grants (is_granted=True) form the base set.
    - User grants (is_granted=True) are added.
    - User denials (is_granted=False) are removed, even if team granted.
    This allows revoking individual permissions at the user level.
    """
    if user._piquano_perms is None:
        from .models import TeamPermission, UserPermission

        perms = set()

        # 1. Team-level permissions as base
        # Try local team FK first, then CRM API fallback (for apps
        # where User model has no team field, e.g. ATS).
        team_id = getattr(user, "team_id", None)
        if not team_id:
            try:
                from django.core.cache import cache

                cache_key = f"piquano_team_id:{user.pk}"
                team_id = cache.get(cache_key)
                if team_id is None:
                    from piquano_core.crm_client import CRMClient

                    data = CRMClient.from_settings().get_user(user.username)
                    team_data = data.get("team")
                    if isinstance(team_data, dict) and team_data.get("id"):
                        team_id = team_data["id"]
                    cache.set(cache_key, team_id or "", 300)  # 5 min
                if not team_id:
                    team_id = None
            except Exception:
                pass
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
            perms = {f"{app}.{module}.{code}" for app, module, code in team_qs}

        # 2. User-level overrides: grants add, denials remove
        user_qs = (
            UserPermission.objects.filter(user=user)
            .select_related("permission")
            .values_list(
                "permission__app_label",
                "permission__module_name",
                "permission__codename",
                "is_granted",
            )
        )
        for app, module, code, granted in user_qs:
            key = f"{app}.{module}.{code}"
            if granted:
                perms.add(key)
            else:
                perms.discard(key)

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
