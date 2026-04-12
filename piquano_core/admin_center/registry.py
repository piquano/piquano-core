"""
App-Registry fuer das Piquano Admin-Center.

Consumer-Apps registrieren ihre Module und Berechtigungen hier.
sync_permissions liest die Registry und erstellt DB-Eintraege.
"""

from __future__ import annotations

_REGISTRY: dict[str, dict[str, list[str]]] = {}


def register_app(app_label: str, modules: dict[str, list[str]]) -> None:
    """Register an app's modules and permissions.

    modules = {"contacts": ["read", "write", "delete"], ...}
    """
    _REGISTRY[app_label] = modules


def get_registry() -> dict[str, dict[str, list[str]]]:
    """Return a copy of the current registry."""
    return _REGISTRY.copy()
