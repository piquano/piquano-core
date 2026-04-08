from django.apps import AppConfig


class AuditConfig(AppConfig):
    name = "piquano_core.audit"
    # Custom label to avoid clashing with apps that already have an "audit"
    # app_label. Do NOT rename — existing migrations are stored under this label.
    label = "piquano_audit"
    default_auto_field = "django.db.models.BigAutoField"
    verbose_name = "PIQUANO Audit Log"
