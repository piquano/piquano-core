"""
Management Command: sync_permissions

Idempotent: liest die Registry, erstellt fehlende FeatureToggle + Permission
Eintraege. Loescht keine bestehenden UserPermission-Zuordnungen.

Usage:
    python manage.py sync_permissions
    python manage.py sync_permissions --app crm
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from piquano_core.admin_center.defaults import (
    PIQUANO_APP_REGISTRY,  # noqa: F401 — triggers registration
)
from piquano_core.admin_center.models import FeatureToggle, Permission
from piquano_core.admin_center.registry import get_registry


class Command(BaseCommand):
    help = "Sync FeatureToggle and Permission entries from the registry."

    def add_arguments(self, parser):
        parser.add_argument(
            "--app",
            type=str,
            default=None,
            help="Only sync a specific app (e.g. 'crm', 'ats').",
        )

    def handle(self, *args, **options):
        from django.conf import settings as django_settings

        registry = get_registry()
        app_filter = options["app"]

        # Default to PIQUANO_APP_NAME if --app not given
        if not app_filter:
            app_filter = getattr(django_settings, "PIQUANO_ADMIN_CENTER_APP", None)

        if app_filter:
            if app_filter not in registry:
                self.stderr.write(self.style.ERROR(f"App '{app_filter}' not found in registry."))
                return
            registry = {app_filter: registry[app_filter]}

        toggles_created = 0
        perms_created = 0

        for app_label, modules in registry.items():
            for module_name, codenames in modules.items():
                # FeatureToggle
                _, created = FeatureToggle.objects.get_or_create(
                    app_label=app_label,
                    module_name=module_name,
                )
                if created:
                    toggles_created += 1

                # Permissions
                for codename in codenames:
                    _, created = Permission.objects.get_or_create(
                        app_label=app_label,
                        module_name=module_name,
                        codename=codename,
                    )
                    if created:
                        perms_created += 1

        self.stdout.write(
            self.style.SUCCESS(
                f"Sync complete: {toggles_created} toggles created, "
                f"{perms_created} permissions created."
            )
        )
