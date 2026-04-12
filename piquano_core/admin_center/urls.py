"""URL-Konfiguration fuer das Piquano Admin-Center."""

from __future__ import annotations

from django.urls import path

from . import views

app_name = "piquano_admin_center"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("toggles/", views.toggle_list, name="toggles"),
    path("toggles/<uuid:pk>/toggle/", views.toggle_switch, name="toggle_switch"),
    path("permissions/", views.permission_overview, name="permissions"),
    path("permissions/<int:user_id>/", views.user_permissions, name="user_permissions"),
    path(
        "permissions/<int:user_id>/save/",
        views.save_user_permissions,
        name="save_permissions",
    ),
]
