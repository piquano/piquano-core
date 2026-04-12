"""
Context Processor: stellt piquano_toggles und piquano_permissions
in allen Templates bereit.

piquano_toggles ist ein dict mit underscore-Keys fuer Template dot-notation:
  {% if piquano_toggles.crm_reports %}
"""

from __future__ import annotations


class _ToggleDict(dict):
    """Dict that supports attribute access for template dot-notation."""

    def __getattr__(self, key):
        return self.get(key, True)  # Default: enabled


def piquano_context(request):
    """Add Piquano permissions and feature toggles to template context."""
    ctx = {
        "piquano_permissions": set(),
        "piquano_toggles": _ToggleDict(),
    }

    if (
        hasattr(request, "user")
        and request.user.is_authenticated
        and hasattr(request.user, "has_piquano_perm")
    ):
        from .middleware import _load_perms, _load_toggles

        ctx["piquano_permissions"] = _load_perms(request.user)
        raw_toggles = _load_toggles(request.user)
        friendly = _ToggleDict()
        for (app, module), enabled in raw_toggles.items():
            friendly[f"{app}_{module}"] = enabled
        ctx["piquano_toggles"] = friendly

    return ctx
