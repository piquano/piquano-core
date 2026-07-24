"""URL-Konfiguration fuer die interne Admin-Center-API."""

from __future__ import annotations

from django.urls import path

from . import api_views

urlpatterns = [
    path("stats/", api_views.api_stats, name="api_stats"),
    path("permissions/", api_views.api_permissions, name="api_permissions"),
    path("toggles/", api_views.api_toggles, name="api_toggles"),
    path("toggles/<uuid:pk>/", api_views.api_toggle_switch, name="api_toggle_switch"),
    path("provision-user/", api_views.api_provision_user, name="api_provision_user"),
    path("users/", api_views.api_users, name="api_users"),
    path(
        "user-permissions/<str:username>/",
        api_views.api_user_permissions,
        name="api_user_permissions",
    ),
    path(
        "user-permissions/<str:username>/save/",
        api_views.api_save_user_permissions,
        name="api_save_user_permissions",
    ),
    path(
        "team-permissions/<uuid:team_id>/",
        api_views.api_team_permissions,
        name="api_team_permissions",
    ),
    path(
        "team-permissions/<uuid:team_id>/save/",
        api_views.api_save_team_permissions,
        name="api_save_team_permissions",
    ),
    # KI-Aufruf-Log (EU AI Act)
    path("ki-log/", api_views.api_ki_log, name="api_ki_log"),
    # Funktionskatalog
    path("catalog/", api_views.api_catalog, name="api_catalog"),
    path(
        "catalog/<str:entity_type>/<uuid:entity_id>/",
        api_views.api_entity_catalog,
        name="api_entity_catalog",
    ),
]
