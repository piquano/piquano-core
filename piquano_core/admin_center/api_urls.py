"""URL-Konfiguration fuer die interne Admin-Center-API."""

from __future__ import annotations

from django.urls import path

from . import api_views

urlpatterns = [
    path("stats/", api_views.api_stats, name="api_stats"),
    path("permissions/", api_views.api_permissions, name="api_permissions"),
    path("toggles/", api_views.api_toggles, name="api_toggles"),
    path("toggles/<uuid:pk>/", api_views.api_toggle_switch, name="api_toggle_switch"),
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
]
