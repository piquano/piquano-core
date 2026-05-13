"""
Context Processor: stellt piquano_toggles, piquano_permissions
und pq_topbar in allen Templates bereit.

piquano_toggles ist ein dict mit underscore-Keys fuer Template dot-notation:
  {% if piquano_toggles.crm_reports %}
"""

from __future__ import annotations

from django.conf import settings
from django.urls import reverse, NoReverseMatch

# Topbar-Konfiguration pro App (Schluessel = PIQUANO_ADMIN_CENTER_APP)
_TOPBAR_APPS = {
    "crm": {"label": "CRM", "search_url": "global_search", "search_placeholder": "Suchen..."},
    "ats": {"label": "ATS", "search_url": "candidates:list", "search_placeholder": "Kandidaten suchen..."},
    "app": {"label": "Hub", "search_url": "partners:list", "search_placeholder": "Partner suchen..."},
    "lms": {"label": "LMS", "search_url": "courses:list", "search_placeholder": "Kurse suchen\u2026"},
    "support": {"label": "Support", "search_url": "tickets:list", "search_placeholder": "Tickets suchen\u2026"},
    "content": {"label": "Content", "search_url": "content:post_list", "search_placeholder": "Posts suchen\u2026"},
}


def _get_ats_badge_count():
    """Return unviewed ATS applications count. Uses DB in ATS, API elsewhere."""
    import logging
    from django.core.cache import cache

    cached = cache.get("ats_new_applications_count")
    if cached is not None:
        return cached

    count = 0
    app_id = getattr(settings, "PIQUANO_ADMIN_CENTER_APP", "")

    if app_id == "ats":
        # Direkt aus der DB lesen (wir sind im ATS)
        try:
            from django.utils import timezone as tz
            from datetime import timedelta
            from jobs.models import Application

            since = tz.now() - timedelta(hours=12)
            count = Application.objects.filter(is_viewed=False, applied_at__gte=since).count()
        except Exception:
            count = 0
    else:
        # API-Call ans ATS
        base_url = getattr(settings, "ATS_API_BASE_URL", "") or ""
        token = getattr(settings, "ATS_API_TOKEN", "") or ""
        if not base_url:
            base_url = getattr(settings, "PIQUANO_ATS_BASE_URL", "") or ""
            if base_url and "/api/" not in base_url:
                base_url = base_url.rstrip("/") + "/api/v1"
        if not token:
            token = getattr(settings, "PIQUANO_ATS_API_TOKEN", "") or ""
        if base_url and token:
            try:
                import requests

                resp = requests.get(
                    f"{base_url.rstrip('/')}/applications/new-count/",
                    headers={"Authorization": f"Token {token}"},
                    timeout=3,
                )
                resp.raise_for_status()
                count = resp.json().get("count", 0)
            except Exception:
                logging.getLogger(__name__).debug("ATS badge API nicht erreichbar")
                count = 0

    cache.set("ats_new_applications_count", count, 60)  # 1 min cache
    return count if count > 0 else 0


class _ToggleDict(dict):
    """Dict for feature toggles. Default: True (features enabled unless explicitly disabled)."""

    def __getattr__(self, key):
        if key.startswith("_"):
            return super().__getattribute__(key)
        return self.get(key, True)


class _PermDict(dict):
    """Dict for permissions. Default: False (denied unless explicitly granted). Admins get True."""

    _bypass = False

    def __getattr__(self, key):
        if key.startswith("_"):
            return super().__getattribute__(key)
        if self._bypass:
            return True
        return self.get(key, False)


def piquano_context(request):
    """Add Piquano permissions and feature toggles to template context.

    Templates can check permissions with dot-notation:
        {% if perms.ats_candidates_read %}
        {% if perms.crm_deals_write %}
    Superusers always get True for all permissions.
    """
    ctx = {
        "piquano_permissions": set(),
        "piquano_toggles": _ToggleDict(),
        "perms_check": _PermDict(),
    }

    if (
        hasattr(request, "user")
        and request.user.is_authenticated
        and hasattr(request.user, "has_piquano_perm")
    ):
        from .middleware import _load_perms, _load_toggles

        perm_set = _load_perms(request.user)
        ctx["piquano_permissions"] = perm_set

        # Template-friendly: "ats.candidates.read" → perms_check.ats_candidates_read = True
        perms_dict = _PermDict()
        perms_dict._bypass = (
            getattr(request.user, "is_superuser", False)
            or getattr(request.user, "is_staff", False)
            or getattr(request.user, "_piquano_is_admin", False)
        )
        for p in perm_set:
            perms_dict[p.replace(".", "_")] = True
        ctx["perms_check"] = perms_dict
        ctx["piquano_is_admin"] = perms_dict._bypass

        raw_toggles = _load_toggles(request.user)
        friendly = _ToggleDict()
        for (app, module), enabled in raw_toggles.items():
            friendly[f"{app}_{module}"] = enabled
        ctx["piquano_toggles"] = friendly

    # ── ATS Badge Count (neue Bewerbungen, 24h) ────────────────────
    if hasattr(request, "user") and request.user.is_authenticated:
        ctx["ats_new_applications_count"] = _get_ats_badge_count()

    # ── Impersonation ──────────────────────────────────────────────
    ctx["is_impersonating"] = getattr(request, "is_impersonating", False)
    ctx["real_user"] = getattr(request, "real_user", request.user)
    ctx["impersonated_user"] = (
        request.user if getattr(request, "is_impersonating", False) else None
    )

    # ── Unified Topbar ──────────────────────────────────────────────
    app_id = getattr(settings, "PIQUANO_ADMIN_CENTER_APP", "crm")
    app_cfg = _TOPBAR_APPS.get(app_id, _TOPBAR_APPS["crm"])
    try:
        search_url = reverse(app_cfg["search_url"])
    except NoReverseMatch:
        search_url = "/"
    ctx["pq_topbar"] = {
        "app_id": app_id,
        "label": app_cfg["label"],
        "search_url": search_url,
        "search_placeholder": app_cfg["search_placeholder"],
    }

    return ctx
