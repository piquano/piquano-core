from __future__ import annotations

from django.contrib import admin

from .models import FeatureToggle, Permission, UserPermission


@admin.register(FeatureToggle)
class FeatureToggleAdmin(admin.ModelAdmin):
    list_display = ("app_label", "module_name", "is_enabled", "updated_at")
    list_filter = ("app_label", "is_enabled")
    search_fields = ("app_label", "module_name")
    readonly_fields = ("id", "updated_at")


@admin.register(Permission)
class PermissionAdmin(admin.ModelAdmin):
    list_display = ("app_label", "module_name", "codename", "description")
    list_filter = ("app_label",)
    search_fields = ("app_label", "module_name", "codename")
    readonly_fields = ("id",)


@admin.register(UserPermission)
class UserPermissionAdmin(admin.ModelAdmin):
    list_display = ("user", "permission", "is_granted", "granted_at", "granted_by")
    list_filter = ("is_granted", "permission__app_label")
    search_fields = ("user__username", "permission__codename")
    readonly_fields = ("id", "granted_at")
    raw_id_fields = ("user", "permission")
