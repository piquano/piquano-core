"""
Context Processor: stellt piquano_toggles und piquano_permissions
in allen Templates bereit.
"""

from __future__ import annotations


def piquano_context(request):
    """Add Piquano permissions and feature toggles to template context."""
    ctx = {
        "piquano_permissions": set(),
        "piquano_toggles": {},
    }

    if (
        hasattr(request, "user")
        and request.user.is_authenticated
        and hasattr(request.user, "has_piquano_perm")
    ):
        from .middleware import _load_perms, _load_toggles

        ctx["piquano_permissions"] = _load_perms(request.user)
        ctx["piquano_toggles"] = _load_toggles(request.user)

    return ctx
