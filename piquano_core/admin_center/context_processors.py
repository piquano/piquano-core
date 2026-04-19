"""
Context Processor: stellt piquano_toggles und piquano_permissions
in allen Templates bereit.

piquano_toggles ist ein dict mit underscore-Keys fuer Template dot-notation:
  {% if piquano_toggles.crm_reports %}
"""

from __future__ import annotations


class _ToggleDict(dict):
    """Dict for feature toggles. Default: True (features enabled unless explicitly disabled)."""

    def __getattr__(self, key):
        if key.startswith("_"):
            return super().__getattribute__(key)
        return self.get(key, True)


class _PermDict(dict):
    """Dict for permissions. Default: False (denied unless explicitly granted). Admins get True."""

    _bypass = False

    def __getattr__(self, key):
        if key.startswith("_"):
            return super().__getattribute__(key)
        if self._bypass:
            return True
        return self.get(key, False)


def piquano_context(request):
    """Add Piquano permissions and feature toggles to template context.

    Templates can check permissions with dot-notation:
        {% if perms.ats_candidates_read %}
        {% if perms.crm_deals_write %}
    Superusers always get True for all permissions.
    """
    ctx = {
        "piquano_permissions": set(),
        "piquano_toggles": _ToggleDict(),
        "perms_check": _PermDict(),
    }

    if (
        hasattr(request, "user")
        and request.user.is_authenticated
        and hasattr(request.user, "has_piquano_perm")
    ):
        from .middleware import _load_perms, _load_toggles

        perm_set = _load_perms(request.user)
        ctx["piquano_permissions"] = perm_set

        # Template-friendly: "ats.candidates.read" → perms_check.ats_candidates_read = True
        perms_dict = _PermDict()
        perms_dict._bypass = (
            getattr(request.user, "is_superuser", False)
            or getattr(request.user, "is_staff", False)
            or getattr(request.user, "_piquano_is_admin", False)
        )
        for p in perm_set:
            perms_dict[p.replace(".", "_")] = True
        ctx["perms_check"] = perms_dict

        raw_toggles = _load_toggles(request.user)
        friendly = _ToggleDict()
        for (app, module), enabled in raw_toggles.items():
            friendly[f"{app}_{module}"] = enabled
        ctx["piquano_toggles"] = friendly

    return ctx
