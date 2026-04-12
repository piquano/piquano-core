from __future__ import annotations

from django.apps import AppConfig


class PiquanoAdminCenterConfig(AppConfig):
    name = "piquano_core.admin_center"
    label = "piquano_admin_center"
    default_auto_field = "django.db.models.UUIDField"
    verbose_name = "Piquano Admin-Center"
