"""
Piquano Admin-Center Models: FeatureToggle, Permission, UserPermission.

Zentrale Berechtigungs- und Feature-Verwaltung fuer alle Piquano-Apps.
db_table ist explizit gesetzt (Muster von piquano_core.ms365).
"""

from __future__ import annotations

import uuid

from django.conf import settings
from django.db import models


class FeatureToggle(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    app_label = models.CharField("App", max_length=50)
    module_name = models.CharField("Modul", max_length=100)
    is_enabled = models.BooleanField("Aktiviert", default=True)
    description = models.TextField("Beschreibung", blank=True)
    updated_at = models.DateTimeField("Aktualisiert", auto_now=True)

    class Meta:
        db_table = "piquano_admin_center_featuretoggle"
        unique_together = [("app_label", "module_name")]
        verbose_name = "Feature-Toggle"
        verbose_name_plural = "Feature-Toggles"
        ordering = ["app_label", "module_name"]

    def __str__(self):
        status = "AN" if self.is_enabled else "AUS"
        return f"{self.app_label}.{self.module_name} [{status}]"


class Permission(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    app_label = models.CharField("App", max_length=50)
    module_name = models.CharField("Modul", max_length=100)
    codename = models.CharField("Berechtigung", max_length=50)
    description = models.CharField("Beschreibung", max_length=200, blank=True)

    class Meta:
        db_table = "piquano_admin_center_permission"
        unique_together = [("app_label", "module_name", "codename")]
        verbose_name = "Berechtigung"
        verbose_name_plural = "Berechtigungen"
        ordering = ["app_label", "module_name", "codename"]

    def __str__(self):
        return f"{self.app_label}.{self.module_name}.{self.codename}"


class UserPermission(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="piquano_permissions",
        verbose_name="Benutzer",
    )
    permission = models.ForeignKey(
        Permission,
        on_delete=models.CASCADE,
        related_name="user_assignments",
        verbose_name="Berechtigung",
    )
    is_granted = models.BooleanField("Erteilt", default=True)
    granted_at = models.DateTimeField("Erteilt am", auto_now_add=True)
    granted_by = models.CharField("Erteilt von", max_length=150, blank=True)

    class Meta:
        db_table = "piquano_admin_center_userpermission"
        unique_together = [("user", "permission")]
        verbose_name = "Benutzer-Berechtigung"
        verbose_name_plural = "Benutzer-Berechtigungen"
        ordering = ["user", "permission"]

    def __str__(self):
        status = "JA" if self.is_granted else "NEIN"
        return f"{self.user} -> {self.permission} [{status}]"
