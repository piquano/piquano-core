"""
Django Database Router for the shared piquano_shared database.

Routes all models from the piquano_core.shared app to the 'shared' database.
All other models go to 'default'.
"""

SHARED_APP_LABEL = "piquano_shared"


class SharedDatabaseRouter:
    """Routes piquano_shared models to the 'shared' database."""

    def db_for_read(self, model, **hints):
        if model._meta.app_label == SHARED_APP_LABEL:
            return "shared"
        return None

    def db_for_write(self, model, **hints):
        if model._meta.app_label == SHARED_APP_LABEL:
            return "shared"
        return None

    def allow_relation(self, obj1, obj2, **hints):
        # Allow relations within the same DB, or if either is shared
        labels = {obj1._meta.app_label, obj2._meta.app_label}
        if SHARED_APP_LABEL in labels:
            return True
        return None

    def allow_migrate(self, db, app_label, model_name=None, **hints):
        if app_label == SHARED_APP_LABEL:
            return db == "shared"
        if db == "shared":
            return False
        return None
