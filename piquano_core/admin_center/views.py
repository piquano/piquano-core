"""Views fuer das Piquano Admin-Center."""

from __future__ import annotations

from collections import defaultdict

from django.conf import settings as django_settings
from django.contrib import messages
from django.contrib.auth import get_user_model
from django.contrib.auth.decorators import login_required
from django.http import HttpResponseForbidden
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .defaults import APP_LABELS, MODULE_LABELS, PERMISSION_LABELS
from .models import FeatureToggle, Permission, TeamPermission, UserPermission


def _get_own_app() -> str | None:
    """Return the PIQUANO_APP_NAME from settings, or None if not set."""
    return getattr(django_settings, "PIQUANO_ADMIN_CENTER_APP", None)


User = get_user_model()


def _app_label(key):
    return APP_LABELS.get(key, key)


def _module_label(app, module):
    return MODULE_LABELS.get(f"{app}.{module}", module)


def _perm_label(codename):
    return PERMISSION_LABELS.get(codename, codename)


def _staff_required(view_func):
    """Decorator: login_required + is_staff / is_superuser."""

    @login_required
    def wrapper(request, *args, **kwargs):
        if not (request.user.is_staff or request.user.is_superuser):
            return HttpResponseForbidden("Kein Zugriff.")
        return view_func(request, *args, **kwargs)

    wrapper.__name__ = view_func.__name__
    wrapper.__doc__ = view_func.__doc__
    return wrapper


@_staff_required
def dashboard(request):
    """Uebersicht: KPIs und Quick-Links."""
    own_app = _get_own_app()
    t_qs = (
        FeatureToggle.objects.filter(app_label=own_app) if own_app else FeatureToggle.objects.all()
    )
    p_qs = Permission.objects.filter(app_label=own_app) if own_app else Permission.objects.all()
    toggles_total = t_qs.count()
    toggles_active = t_qs.filter(is_enabled=True).count()
    permissions_total = p_qs.count()
    users_with_perms = (
        UserPermission.objects.filter(is_granted=True).values("user").distinct().count()
    )
    return render(
        request,
        "piquano_admin_center/dashboard.html",
        {
            "toggles_total": toggles_total,
            "toggles_active": toggles_active,
            "toggles_inactive": toggles_total - toggles_active,
            "permissions_total": permissions_total,
            "users_with_perms": users_with_perms,
        },
    )


@_staff_required
def toggle_list(request):
    """Feature-Toggles der eigenen App, gruppiert nach app_label."""
    own_app = _get_own_app()
    toggles = (
        FeatureToggle.objects.filter(app_label=own_app) if own_app else FeatureToggle.objects.all()
    )
    grouped: dict[str, dict] = {}
    for t in toggles:
        if t.app_label not in grouped:
            grouped[t.app_label] = {"label": _app_label(t.app_label), "toggles": []}
        t.display_name = _module_label(t.app_label, t.module_name)
        grouped[t.app_label]["toggles"].append(t)
    grouped_sorted = dict(sorted(grouped.items()))
    return render(
        request,
        "piquano_admin_center/toggle_list.html",
        {"grouped_toggles": grouped_sorted},
    )


@require_POST
@_staff_required
def toggle_switch(request, pk):
    """Schaltet einen Feature-Toggle um."""
    toggle = get_object_or_404(FeatureToggle, pk=pk)
    toggle.is_enabled = not toggle.is_enabled
    toggle.save(update_fields=["is_enabled", "updated_at"])
    status = "aktiviert" if toggle.is_enabled else "deaktiviert"
    label = _module_label(toggle.app_label, toggle.module_name)
    messages.success(request, f"{label} ({_app_label(toggle.app_label)}) {status}.")
    return redirect("piquano_admin_center:toggles")


@_staff_required
def permission_overview(request):
    """Liste aller User mit Anzahl zugewiesener Permissions."""
    users = User.objects.filter(is_active=True).order_by("username")
    user_data = []
    for user in users:
        perm_count = UserPermission.objects.filter(user=user, is_granted=True).count()
        user_data.append(
            {
                "id": user.id,
                "username": user.username,
                "full_name": user.get_full_name() or user.username,
                "email": user.email,
                "perm_count": perm_count,
            }
        )
    return render(
        request,
        "piquano_admin_center/permission_overview.html",
        {"user_data": user_data},
    )


@_staff_required
def user_permissions(request, user_id):
    """Matrix-View: Permissions der eigenen App als Checkboxen fuer einen User."""
    target_user = get_object_or_404(User, pk=user_id)
    own_app = _get_own_app()
    permissions = (
        Permission.objects.filter(app_label=own_app) if own_app else Permission.objects.all()
    )

    # Current grants for this user
    granted_ids = set(
        UserPermission.objects.filter(user=target_user, is_granted=True).values_list(
            "permission_id", flat=True
        )
    )

    # Group by app_label > module_name
    grouped: dict[str, dict] = {}
    for perm in permissions:
        if perm.app_label not in grouped:
            grouped[perm.app_label] = {
                "label": _app_label(perm.app_label),
                "modules": defaultdict(list),
            }
        grouped[perm.app_label]["modules"][perm.module_name].append(
            {
                "id": str(perm.id),
                "codename": perm.codename,
                "codename_label": _perm_label(perm.codename),
                "module_label": _module_label(perm.app_label, perm.module_name),
                "granted": perm.id in granted_ids,
            }
        )

    # Sort for consistent rendering: modules alphabetically, permissions read → write → delete
    codename_order = {"read": 0, "write": 1, "delete": 2}
    grouped_sorted = {}
    for app, data in sorted(grouped.items()):
        sorted_modules = {}
        for module, perms in sorted(data["modules"].items()):
            sorted_modules[module] = sorted(perms, key=lambda p: codename_order.get(p["codename"], 9))
        grouped_sorted[app] = {"label": data["label"], "modules": sorted_modules}

    return render(
        request,
        "piquano_admin_center/user_permissions.html",
        {
            "target_user": target_user,
            "grouped_permissions": grouped_sorted,
        },
    )


@require_POST
@_staff_required
def save_user_permissions(request, user_id):
    """Bulk-Update der UserPermission-Eintraege (nur eigene App)."""
    target_user = get_object_or_404(User, pk=user_id)
    granted_perm_ids = set(request.POST.getlist("permissions"))
    own_app = _get_own_app()
    all_permissions = (
        Permission.objects.filter(app_label=own_app) if own_app else Permission.objects.all()
    )

    for perm in all_permissions:
        should_grant = str(perm.id) in granted_perm_ids
        up, created = UserPermission.objects.get_or_create(
            user=target_user,
            permission=perm,
            defaults={
                "is_granted": should_grant,
                "granted_by": request.user.username,
            },
        )
        if not created and up.is_granted != should_grant:
            up.is_granted = should_grant
            up.granted_by = request.user.username
            up.save(update_fields=["is_granted", "granted_by"])

    messages.success(
        request,
        f"Berechtigungen fuer {target_user.get_full_name() or target_user.username} gespeichert.",
    )
    return redirect("piquano_admin_center:user_permissions", user_id=user_id)


@_staff_required
def team_permission_overview(request):
    """Liste aller Teams mit Anzahl zugewiesener Permissions."""
    # Teams kommen aus der consumer-App (CRM hat Team-Model, andere nicht).
    # Wir lesen nur die team_ids aus TeamPermission.
    from django.contrib.auth import get_user_model

    UserModel = get_user_model()

    # Teams aus User-Tabelle (alle team_ids die vergeben sind)
    team_ids_from_users = set(
        UserModel.objects.exclude(team_id__isnull=True)
        .values_list("team_id", flat=True)
        .distinct()
    ) if hasattr(UserModel, "team") else set()

    # Teams aus TeamPermission (könnten auch Teams ohne User haben)
    team_ids_from_perms = set(
        TeamPermission.objects.values_list("team_id", flat=True).distinct()
    )

    all_team_ids = team_ids_from_users | team_ids_from_perms

    # Team-Namen laden falls Team-Model existiert
    team_names = {}
    if hasattr(UserModel, "team"):
        TeamModel = UserModel.team.field.related_model
        for t in TeamModel.objects.filter(pk__in=all_team_ids):
            team_names[t.pk] = t.name

    team_data = []
    for tid in sorted(all_team_ids, key=lambda x: team_names.get(x, str(x))):
        perm_count = TeamPermission.objects.filter(team_id=tid, is_granted=True).count()
        member_count = UserModel.objects.filter(team_id=tid, is_active=True).count() if hasattr(UserModel, "team") else 0
        team_data.append({
            "id": tid,
            "name": team_names.get(tid, str(tid)),
            "perm_count": perm_count,
            "member_count": member_count,
        })

    return render(
        request,
        "piquano_admin_center/team_permission_overview.html",
        {"team_data": team_data},
    )


@_staff_required
def team_permissions(request, team_id):
    """Matrix-View: Permissions als Checkboxen fuer ein Team."""
    import uuid as _uuid

    team_uuid = _uuid.UUID(str(team_id))
    own_app = _get_own_app()
    permissions = (
        Permission.objects.filter(app_label=own_app) if own_app else Permission.objects.all()
    )

    granted_ids = set(
        TeamPermission.objects.filter(team_id=team_uuid, is_granted=True).values_list(
            "permission_id", flat=True
        )
    )

    # Team-Name laden
    team_name = str(team_uuid)
    try:
        from django.contrib.auth import get_user_model
        UserModel = get_user_model()
        if hasattr(UserModel, "team"):
            TeamModel = UserModel.team.field.related_model
            team_obj = TeamModel.objects.filter(pk=team_uuid).first()
            if team_obj:
                team_name = team_obj.name
    except Exception:
        pass

    grouped: dict[str, dict] = {}
    for perm in permissions:
        if perm.app_label not in grouped:
            grouped[perm.app_label] = {
                "label": _app_label(perm.app_label),
                "modules": defaultdict(list),
            }
        grouped[perm.app_label]["modules"][perm.module_name].append(
            {
                "id": str(perm.id),
                "codename": perm.codename,
                "codename_label": _perm_label(perm.codename),
                "module_label": _module_label(perm.app_label, perm.module_name),
                "granted": perm.id in granted_ids,
            }
        )

    codename_order = {"read": 0, "write": 1, "delete": 2}
    grouped_sorted = {}
    for app, data in sorted(grouped.items()):
        sorted_modules = {}
        for module, perms in sorted(data["modules"].items()):
            sorted_modules[module] = sorted(perms, key=lambda p: codename_order.get(p["codename"], 9))
        grouped_sorted[app] = {"label": data["label"], "modules": sorted_modules}

    return render(
        request,
        "piquano_admin_center/team_permissions.html",
        {
            "team_id": team_uuid,
            "team_name": team_name,
            "grouped_permissions": grouped_sorted,
        },
    )


@require_POST
@_staff_required
def save_team_permissions(request, team_id):
    """Bulk-Update der TeamPermission-Eintraege."""
    import uuid as _uuid

    team_uuid = _uuid.UUID(str(team_id))
    granted_perm_ids = set(request.POST.getlist("permissions"))
    own_app = _get_own_app()
    all_permissions = (
        Permission.objects.filter(app_label=own_app) if own_app else Permission.objects.all()
    )

    for perm in all_permissions:
        should_grant = str(perm.id) in granted_perm_ids
        tp, created = TeamPermission.objects.get_or_create(
            team_id=team_uuid,
            permission=perm,
            defaults={
                "is_granted": should_grant,
                "granted_by": request.user.username,
            },
        )
        if not created and tp.is_granted != should_grant:
            tp.is_granted = should_grant
            tp.granted_by = request.user.username
            tp.save(update_fields=["is_granted", "granted_by"])

    messages.success(request, f"Team-Berechtigungen gespeichert.")
    return redirect("piquano_admin_center:team_permissions", team_id=team_uuid)


@_staff_required
def system_status(request):
    """System-Status Dashboard mit Live-Metriken."""
    grafana_url = getattr(django_settings, "PIQUANO_GRAFANA_URL", "https://metrics.piquano.com")

    # API-Endpoint für AJAX-Metriken
    if request.path.endswith("/api/metrics/"):
        return _system_metrics_api(request)

    return render(
        request,
        "piquano_admin_center/system_status.html",
        {"grafana_url": grafana_url},
    )


def _system_metrics_api(request):
    """JSON-API: Prometheus-Metriken + Service-Status."""
    import json
    import subprocess
    import urllib.request
    from django.http import JsonResponse

    data = {"cpu": None, "ram": None, "disk": None, "uptime_days": None, "services": []}

    # Prometheus-Queries
    prom = "http://127.0.0.1:9090/api/v1/query"
    queries = {
        "cpu": '100 - (avg(rate(node_cpu_seconds_total{mode="idle"}[5m])) * 100)',
        "ram": '(1 - node_memory_MemAvailable_bytes / node_memory_MemTotal_bytes) * 100',
        "disk": '(1 - node_filesystem_avail_bytes{mountpoint="/"} / node_filesystem_size_bytes{mountpoint="/"}) * 100',
        "uptime": "node_time_seconds - node_boot_time_seconds",
    }

    for key, query in queries.items():
        try:
            url = f"{prom}?query={urllib.parse.quote(query)}"
            with urllib.request.urlopen(url, timeout=3) as resp:
                result = json.loads(resp.read())
                if result.get("data", {}).get("result"):
                    val = float(result["data"]["result"][0]["value"][1])
                    if key == "uptime":
                        data["uptime_days"] = int(val / 86400)
                    else:
                        data[key] = round(val, 1)
        except Exception:
            pass

    # Service-Status via Port-Check + Response-Zeit
    import socket
    import time as _time

    services = [
        ("CRM", 5003),
        ("ATS", 5006),
        ("App", 5005),
        ("LMS", 5008),
        ("Support", 5009),
        ("Prometheus", 9090),
        ("Grafana", 3000),
    ]
    for name, port in services:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
            s.settimeout(2)
            t0 = _time.monotonic()
            result = s.connect_ex(("127.0.0.1", port))
            ms = round((_time.monotonic() - t0) * 1000)
            s.close()
            data["services"].append({"name": name, "active": result == 0, "ms": ms if result == 0 else None})
        except Exception:
            data["services"].append({"name": name, "active": False, "ms": None})

    # DB-Größen
    try:
        from django.db import connections
        with connections["default"].cursor() as cur:
            cur.execute("""
                SELECT datname, pg_database_size(datname)
                FROM pg_database
                WHERE datname LIKE 'piquano_%' AND datname NOT LIKE '%staging%'
                ORDER BY pg_database_size(datname) DESC
            """)
            data["databases"] = [
                {"name": row[0], "size_mb": round(row[1] / 1024 / 1024, 1)}
                for row in cur.fetchall()
            ]
    except Exception:
        data["databases"] = []

    # Letztes Backup
    import glob
    import os
    try:
        log_dir = "/var/log/piquano/"
        logs = sorted(glob.glob(f"{log_dir}pg-backup-*.log"), reverse=True)
        if logs:
            mtime = os.path.getmtime(logs[0])
            from datetime import datetime
            data["last_backup"] = {
                "file": os.path.basename(logs[0]),
                "date": datetime.fromtimestamp(mtime).strftime("%d.%m.%Y %H:%M"),
                "ok": "Remote-Verify bestanden" in open(logs[0]).read(),
            }
    except Exception:
        data["last_backup"] = None

    return JsonResponse(data)


@_staff_required
def docs_page(request, page):
    """Statische Dokumentationsseiten (Admin-Handbuch, TOM, VVT)."""
    return render(request, f"piquano_admin_center/docs/{page}.html")
