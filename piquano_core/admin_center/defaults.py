"""
Default-Registrierungen fuer alle Piquano-Apps.

Wird beim Import automatisch in die Registry eingetragen.
"""

from __future__ import annotations

from .registry import register_app

PIQUANO_APP_REGISTRY: dict[str, dict[str, list[str]]] = {
    "crm": {
        "contacts": ["read", "write", "delete"],
        "deals": ["read", "write", "delete"],
        "activities": ["read", "write"],
        "emails": ["read", "write"],
        "briefings": ["read", "write"],
        "reports": ["read"],
        "workflows": ["read", "write"],
        "integrations": ["read", "write"],
        "ms365": ["read", "write"],
        "timeline": ["read"],
        "accounts": ["read", "write", "delete"],
    },
    "ats": {
        "candidates": ["read", "write", "delete"],
        "jobs": ["read", "write", "delete"],
        "careers": ["read", "write"],
        "mail": ["read", "write"],
        "reports": ["read"],
        "pipeline": ["read", "write"],
    },
    "app": {
        "partners": ["read", "write"],
        "casestudies": ["read", "write", "delete"],
        "wettbewerb": ["read", "write"],
        "ki_beitrag": ["read", "write"],
        "linkedin_review": ["read", "write"],
        "vertriebscoach": ["read"],
        "activities": ["read"],
    },
    "lms": {
        "courses": ["read", "write", "delete"],
        "lessons": ["read", "write", "delete"],
        "enrollments": ["read", "write"],
        "certificates": ["read", "write"],
        "progress": ["read"],
    },
    "ticket": {
        "tickets": ["read", "write", "delete"],
        "comments": ["read", "write"],
        "categories": ["read", "write"],
        "assignments": ["read", "write"],
        "reports": ["read"],
    },
}

# Register all apps on import
for _app_label, _modules in PIQUANO_APP_REGISTRY.items():
    register_app(_app_label, _modules)
