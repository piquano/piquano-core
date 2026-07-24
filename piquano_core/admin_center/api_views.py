"""
Interne REST-API fuer das Piquano Admin-Center.

Ermoeglicht dem zentralen Hub-Admin-Center, Permissions/Toggles/UserPermissions/
TeamPermissions jeder App per API zu lesen und zu schreiben.

Auth: Token-basiert (DRF TokenAuthentication).
"""

from __future__ import annotations

import logging

from django.conf import settings
from django.http import JsonResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_GET, require_http_methods

from .defaults import MODULE_LABELS, PERMISSION_LABELS
from .models import FeatureToggle, Permission, TeamPermission, UserPermission
from .views import _get_own_app

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Auth helper
# ---------------------------------------------------------------------------

def _check_api_token(request) -> bool:
    """Validate internal API token from Authorization header."""
    import os
    auth = request.META.get("HTTP_AUTHORIZATION", "")
    if not auth.startswith("Token "):
        return False
    token = auth[6:].strip()
    if not token:
        return False
    # Check dedicated admin-center token (from env or settings)
    expected = os.environ.get(
        "PIQUANO_ADMIN_CENTER_API_TOKEN",
        getattr(settings, "PIQUANO_ADMIN_CENTER_API_TOKEN", ""),
    )
    if expected and token == expected:
        return True
    # Fallback: validate against DRF authtoken table
    try:
        from rest_framework.authtoken.models import Token
        return Token.objects.filter(key=token).exists()
    except Exception:
        return False


def _require_api_token(view_func):
    """Decorator: reject requests without valid internal API token."""
    def wrapper(request, *args, **kwargs):
        if not _check_api_token(request):
            return JsonResponse({"error": "Unauthorized"}, status=401)
        return view_func(request, *args, **kwargs)
    return wrapper


def _get_app_label():
    """Return this app's PIQUANO_ADMIN_CENTER_APP label."""
    return getattr(settings, "PIQUANO_ADMIN_CENTER_APP", "unknown")


# Feste Sortierreihenfolge: Lesen, Bearbeiten, Loeschen
_CODENAME_ORDER = {"read": 0, "write": 1, "delete": 2}


def _sort_permissions(perms: list[dict]) -> list[dict]:
    """Sort permissions by module_name, then codename (read, write, delete)."""
    return sorted(perms, key=lambda p: (
        p.get("module_name", ""),
        _CODENAME_ORDER.get(p.get("codename", ""), 9),
    ))


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------

@csrf_exempt
@require_GET
@_require_api_token
def api_stats(request):
    """KPIs: Toggle-Count, Permission-Count, Users mit Permissions."""
    app = _get_app_label()
    t_total = FeatureToggle.objects.count()
    t_active = FeatureToggle.objects.filter(is_enabled=True).count()
    p_total = Permission.objects.count()
    u_with_perms = (
        UserPermission.objects.filter(is_granted=True)
        .values("user")
        .distinct()
        .count()
    )
    return JsonResponse({
        "app_label": app,
        "toggles_total": t_total,
        "toggles_active": t_active,
        "permissions_total": p_total,
        "users_with_perms": u_with_perms,
    })


# ---------------------------------------------------------------------------
# Permissions (read-only — defined by registry, not editable)
# ---------------------------------------------------------------------------

@csrf_exempt
@require_GET
@_require_api_token
def api_permissions(request):
    """Alle Permission-Objekte dieser App."""
    own_app = _get_own_app()
    qs = Permission.objects.filter(app_label=own_app) if own_app else Permission.objects.all()
    perms = qs.values(
        "id", "app_label", "module_name", "codename", "description",
    )
    result = []
    for p in perms:
        p["module_label"] = MODULE_LABELS.get(
            f"{p['app_label']}.{p['module_name']}", p["module_name"]
        )
        p["codename_label"] = PERMISSION_LABELS.get(p["codename"], p["codename"])
        p["id"] = str(p["id"])
        result.append(p)
    return JsonResponse({"permissions": result})


# ---------------------------------------------------------------------------
# Feature Toggles (read + write)
# ---------------------------------------------------------------------------

@csrf_exempt
@require_GET
@_require_api_token
def api_toggles(request):
    """Alle FeatureToggles dieser App."""
    toggles = FeatureToggle.objects.all().values(
        "id", "app_label", "module_name", "is_enabled", "description",
    )
    result = []
    for t in toggles:
        t["module_label"] = MODULE_LABELS.get(
            f"{t['app_label']}.{t['module_name']}", t["module_name"]
        )
        t["id"] = str(t["id"])
        result.append(t)
    return JsonResponse({"toggles": result})


@csrf_exempt
@require_http_methods(["PUT"])
@_require_api_token
def api_toggle_switch(request, pk):
    """Toggle an/aus schalten."""
    import json
    try:
        toggle = FeatureToggle.objects.get(pk=pk)
    except FeatureToggle.DoesNotExist:
        return JsonResponse({"error": "Toggle nicht gefunden"}, status=404)
    try:
        data = json.loads(request.body)
        toggle.is_enabled = data.get("is_enabled", not toggle.is_enabled)
        toggle.save(update_fields=["is_enabled", "updated_at"])
    except (json.JSONDecodeError, ValueError):
        # Simple toggle without body
        toggle.is_enabled = not toggle.is_enabled
        toggle.save(update_fields=["is_enabled", "updated_at"])
    return JsonResponse({
        "id": str(toggle.pk),
        "is_enabled": toggle.is_enabled,
    })


# ---------------------------------------------------------------------------
# User Permissions (read + write)
# ---------------------------------------------------------------------------

@csrf_exempt
@require_GET
@_require_api_token
def api_user_permissions(request, username):
    """UserPermissions eines Users (identifiziert per username)."""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    user = User.objects.filter(username=username).first()

    own_app = _get_own_app()
    all_perms = Permission.objects.filter(app_label=own_app) if own_app else Permission.objects.all()

    # Direct user permissions (nur wenn User lokal existiert)
    user_granted_ids = set()
    user_denied_ids = set()
    if user:
        user_granted_ids = set(
            UserPermission.objects.filter(user=user, is_granted=True)
            .values_list("permission_id", flat=True)
        )
        user_denied_ids = set(
            UserPermission.objects.filter(user=user, is_granted=False)
            .values_list("permission_id", flat=True)
        )

    # Team permissions (inherited)
    # team_id kommt als Query-Parameter vom Hub (vermeidet CRM-API-Kaskade)
    # oder wird lokal aufgeloest (CRM hat das Feld direkt)
    team_id = request.GET.get("team_id") or (getattr(user, "team_id", None) if user else None)
    team_granted_ids = set()
    if team_id:
        team_granted_ids = set(
            TeamPermission.objects.filter(team_id=team_id, is_granted=True)
            .values_list("permission_id", flat=True)
        )

    result = []
    for p in all_perms:
        # Effective: team grants as base, user overrides
        from_team = p.id in team_granted_ids
        from_user = p.id in user_granted_ids
        denied = p.id in user_denied_ids
        effective = (from_team or from_user) and not denied

        result.append({
            "id": str(p.id),
            "app_label": p.app_label,
            "module_name": p.module_name,
            "codename": p.codename,
            "module_label": MODULE_LABELS.get(f"{p.app_label}.{p.module_name}", p.module_name),
            "codename_label": PERMISSION_LABELS.get(p.codename, p.codename),
            "granted": effective,
            "source": "team" if (from_team and not from_user) else ("user" if from_user else ""),
        })

    return JsonResponse({
        "username": username,
        "user_id": str(user.pk) if user else None,
        "permissions": _sort_permissions(result),
    })


@csrf_exempt
@require_http_methods(["PUT"])
@_require_api_token
def api_save_user_permissions(request, username):
    """UserPermissions setzen (Bulk). Body: {"granted_ids": ["uuid", ...]}"""
    import json

    from django.contrib.auth import get_user_model
    User = get_user_model()

    try:
        user = User.objects.get(username=username)
    except User.DoesNotExist:
        # User existiert auf dieser App nicht — automatisch anlegen
        user = User(username=username, is_active=True)
        user.set_unusable_password()
        user.save()
        logger.info("Auto-provisioned user %s for permission assignment", username)

    try:
        data = json.loads(request.body)
        granted_ids = set(data.get("granted_ids", []))
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Ungueltige Daten"}, status=400)

    # Team-Grants ermitteln (team_id aus Query-Param oder lokal)
    team_id = request.GET.get("team_id") or getattr(user, "team_id", None)
    team_granted_ids = set()
    if team_id:
        team_granted_ids = set(
            TeamPermission.objects.filter(team_id=team_id, is_granted=True)
            .values_list("permission_id", flat=True)
        )

    own_app = _get_own_app()
    all_perms = Permission.objects.filter(app_label=own_app) if own_app else Permission.objects.all()
    changed = 0

    for perm in all_perms:
        should_grant = str(perm.id) in granted_ids
        from_team = perm.id in team_granted_ids

        if from_team and should_grant:
            # Team deckt das ab — keinen UserPermission-Eintrag noetig
            # Bestehenden loeschen falls vorhanden
            deleted, _ = UserPermission.objects.filter(user=user, permission=perm).delete()
            if deleted:
                changed += 1
        elif not from_team and should_grant:
            # User-Grant zusaetzlich zum Team
            up, created = UserPermission.objects.get_or_create(
                user=user, permission=perm,
                defaults={"is_granted": True, "granted_by": "admin-center-api"},
            )
            if not created and not up.is_granted:
                up.is_granted = True
                up.granted_by = "admin-center-api"
                up.save(update_fields=["is_granted", "granted_by"])
                changed += 1
            elif created:
                changed += 1
        elif from_team and not should_grant:
            # Team erlaubt, aber User soll entzogen werden — User-Denial
            up, created = UserPermission.objects.get_or_create(
                user=user, permission=perm,
                defaults={"is_granted": False, "granted_by": "admin-center-api"},
            )
            if not created and up.is_granted:
                up.is_granted = False
                up.granted_by = "admin-center-api"
                up.save(update_fields=["is_granted", "granted_by"])
                changed += 1
            elif created:
                changed += 1
        else:
            # Weder Team noch User — loeschen falls vorhanden
            deleted, _ = UserPermission.objects.filter(user=user, permission=perm).delete()
            if deleted:
                changed += 1

    return JsonResponse({"ok": True, "changed": changed})


# ---------------------------------------------------------------------------
# Team Permissions (read + write)
# ---------------------------------------------------------------------------

@csrf_exempt
@require_GET
@_require_api_token
def api_team_permissions(request, team_id):
    """TeamPermissions eines Teams."""
    own_app = _get_own_app()
    all_perms = Permission.objects.filter(app_label=own_app) if own_app else Permission.objects.all()
    granted_ids = set(
        TeamPermission.objects.filter(team_id=team_id, is_granted=True)
        .values_list("permission_id", flat=True)
    )

    result = []
    for p in all_perms:
        result.append({
            "id": str(p.id),
            "app_label": p.app_label,
            "module_name": p.module_name,
            "codename": p.codename,
            "module_label": MODULE_LABELS.get(f"{p.app_label}.{p.module_name}", p.module_name),
            "codename_label": PERMISSION_LABELS.get(p.codename, p.codename),
            "granted": p.id in granted_ids,
        })

    return JsonResponse({
        "team_id": str(team_id),
        "permissions": _sort_permissions(result),
    })


@csrf_exempt
@require_http_methods(["PUT"])
@_require_api_token
def api_save_team_permissions(request, team_id):
    """TeamPermissions setzen (Bulk). Body: {"granted_ids": ["uuid", ...]}"""
    import json
    try:
        data = json.loads(request.body)
        granted_ids = set(data.get("granted_ids", []))
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Ungueltige Daten"}, status=400)

    own_app = _get_own_app()
    all_perms = Permission.objects.filter(app_label=own_app) if own_app else Permission.objects.all()
    changed = 0

    for perm in all_perms:
        should_grant = str(perm.id) in granted_ids
        tp, created = TeamPermission.objects.get_or_create(
            team_id=team_id,
            permission=perm,
            defaults={"is_granted": should_grant, "granted_by": "admin-center-api"},
        )
        if not created and tp.is_granted != should_grant:
            tp.is_granted = should_grant
            tp.granted_by = "admin-center-api"
            tp.save(update_fields=["is_granted", "granted_by"])
            changed += 1
        elif created:
            changed += 1

    # Delete denials to keep DB clean
    TeamPermission.objects.filter(team_id=team_id, is_granted=False).delete()

    return JsonResponse({"ok": True, "changed": changed})


# ---------------------------------------------------------------------------
# User provisioning (called by Hub on account activation)
# ---------------------------------------------------------------------------


@csrf_exempt
@require_http_methods(["POST"])
@_require_api_token
def api_provision_user(request):
    """Provision a user in this app's local database.

    Called by the Hub when a new user activates their account, so the user
    exists in all app databases from day one (not just on first visit).

    Body: {"username": "...", "first_name": "...", "last_name": "...",
           "email": "...", "is_staff": false, "is_active": true}

    Idempotent: if the user already exists, missing fields are updated.
    """
    import json

    from django.contrib.auth import get_user_model

    User = get_user_model()

    try:
        data = json.loads(request.body)
    except (json.JSONDecodeError, ValueError):
        return JsonResponse({"error": "Ungueltige Daten"}, status=400)

    username = data.get("username", "").strip()
    if not username:
        return JsonResponse({"error": "username ist Pflichtfeld"}, status=400)

    defaults = {"is_active": data.get("is_active", True)}
    for field in ("first_name", "last_name", "email"):
        if data.get(field):
            defaults[field] = data[field]
    if "is_staff" in data:
        defaults["is_staff"] = bool(data["is_staff"])

    user, created = User.objects.get_or_create(
        username=username,
        defaults=defaults,
    )

    if created:
        user.set_unusable_password()
        user.save(update_fields=["password"])
        # Assign default permissions
        try:
            from piquano_core.admin_center.permissions import assign_default_permissions

            assign_default_permissions(user)
        except Exception:
            logger.warning("Could not assign default permissions for %s", username)
        logger.info("Provisioned user %s via API", username)
    else:
        # Update fields that may have been empty from middleware auto-provision
        update_fields = []
        for field in ("first_name", "last_name", "email"):
            new_val = data.get(field)
            if new_val and not getattr(user, field):
                setattr(user, field, new_val)
                update_fields.append(field)
        if update_fields:
            user.save(update_fields=update_fields)
            logger.info("Updated provisioned user %s: %s", username, ", ".join(update_fields))

    return JsonResponse({
        "ok": True,
        "username": username,
        "created": created,
    })


# ---------------------------------------------------------------------------
# Users list (for permission overview — which users exist in this app)
# ---------------------------------------------------------------------------

@csrf_exempt
@require_GET
@_require_api_token
def api_users(request):
    """Alle aktiven User dieser App mit Team-Info."""
    from django.contrib.auth import get_user_model
    User = get_user_model()
    users = User.objects.filter(is_active=True).order_by("username")

    result = []
    for u in users:
        team = getattr(u, "team", None)
        result.append({
            "username": u.username,
            "user_id": str(u.pk),
            "first_name": u.first_name,
            "last_name": u.last_name,
            "email": u.email,
            "is_staff": u.is_staff,
            "is_superuser": u.is_superuser,
            "team_id": str(team.pk) if team else None,
            "team_name": team.name if team else None,
        })

    return JsonResponse({"users": result})


# ---------------------------------------------------------------------------
# Funktionskatalog-API
# ---------------------------------------------------------------------------

@csrf_exempt
@require_GET
@_require_api_token
def api_catalog(request):
    """Gibt den vollständigen Funktionskatalog als JSON zurück.

    Response:
    {
        "verticals": [
            {
                "id": "...", "name": "...", "slug": "...",
                "sub_funktionen": [
                    {"id": "...", "name": "...", "slug": "..."},
                    ...
                ]
            },
            ...
        ]
    }
    """
    from piquano_core.shared.models import Vertical

    verticals = (
        Vertical.objects.using("shared")
        .prefetch_related("sub_funktionen")
        .order_by("sort_order", "name")
    )

    result = []
    for v in verticals:
        result.append({
            "id": str(v.id),
            "name": v.name,
            "slug": v.slug,
            "sub_funktionen": [
                {"id": str(sf.id), "name": sf.name, "slug": sf.slug}
                for sf in v.sub_funktionen.order_by("sort_order", "name")
            ],
        })

    return JsonResponse({"verticals": result})


@csrf_exempt
@require_GET
@_require_api_token
def api_entity_catalog(request, entity_type, entity_id):
    """Gibt die Katalog-Zuordnungen einer Person zurück.

    GET /api/catalog/ats_candidate/<uuid>/
    GET /api/catalog/crm_contact/<uuid>/

    Response:
    {
        "assignments": [
            {"vertical": "...", "sub_funktion": "...", "sub_funktion_id": "..."},
            ...
        ]
    }
    """
    from piquano_core.shared.models import CatalogAssignment

    assignments = (
        CatalogAssignment.objects.using("shared")
        .filter(entity_type=entity_type, entity_id=entity_id)
        .select_related("sub_funktion__vertical")
    )

    result = []
    for a in assignments:
        result.append({
            "vertical": a.sub_funktion.vertical.name,
            "vertical_slug": a.sub_funktion.vertical.slug,
            "sub_funktion": a.sub_funktion.name,
            "sub_funktion_slug": a.sub_funktion.slug,
            "sub_funktion_id": str(a.sub_funktion.id),
        })

    return JsonResponse({"assignments": result})


# ---------------------------------------------------------------------------
# KI-Aufruf-Log (EU AI Act Art. 12) — nur vom ATS bereitgestellt
# ---------------------------------------------------------------------------

@csrf_exempt
@require_GET
def api_ki_log(request):
    """KI-Aufruf-Protokoll für den Hub Admin Center Logfiles-Bereich.

    Nur verfügbar wenn die App ein AICallLog-Model hat (ATS).
    Andere Apps liefern leere Ergebnisliste zurück.
    """
    if not _check_api_token(request):
        return JsonResponse({"error": "Unauthorized"}, status=401)

    try:
        from candidates.ai_log import AICallLog, AICallLog as _M
    except ImportError:
        return JsonResponse({"results": [], "total": 0, "num_pages": 1, "page": 1})

    from django.core.paginator import Paginator

    qs = AICallLog.objects.all()

    system = request.GET.get("system", "").strip()
    status = request.GET.get("status", "").strip()
    date_from = request.GET.get("date_from", "").strip()
    date_to = request.GET.get("date_to", "").strip()
    page_num = request.GET.get("page", "1")
    per_page_raw = request.GET.get("per_page", "50")
    try:
        per_page = min(int(per_page_raw), 5000)
    except (ValueError, TypeError):
        per_page = 50

    if system:
        qs = qs.filter(system=system)
    if status:
        qs = qs.filter(status=status)
    if date_from:
        qs = qs.filter(created_at__date__gte=date_from)
    if date_to:
        qs = qs.filter(created_at__date__lte=date_to)

    paginator = Paginator(qs, per_page)
    page_obj = paginator.get_page(page_num)

    results = [
        {
            "id": str(e.id),
            "system": e.system,
            "system_display": e.get_system_display(),
            "status": e.status,
            "status_display": e.get_status_display(),
            "triggered_by": e.triggered_by,
            "candidate_id": e.candidate_id,
            "job_id": e.job_id,
            "model_id": e.model_id,
            "input_summary": e.input_summary,
            "output_summary": e.output_summary,
            "error_message": e.error_message,
            "created_at": e.created_at.strftime("%Y-%m-%d %H:%M:%S"),
        }
        for e in page_obj
    ]

    return JsonResponse({
        "results": results,
        "total": paginator.count,
        "num_pages": paginator.num_pages,
        "page": page_obj.number,
        "system_choices": AICallLog.SYSTEM_CHOICES,
        "status_choices": AICallLog.STATUS_CHOICES,
    })
