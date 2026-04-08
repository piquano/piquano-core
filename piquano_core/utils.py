"""Shared utilities used by multiple piquano-core modules."""
from __future__ import annotations

import ipaddress
from typing import Iterable

from django.db import models


def get_client_ip(request) -> str | None:
    """Extract the client IP from a request behind a trusted proxy.

    Honors ``X-Forwarded-For`` only when ``REMOTE_ADDR`` is in
    ``settings.PIQUANO_TRUSTED_PROXIES`` (a list/tuple of IPs or CIDRs).
    Falls back to ``REMOTE_ADDR`` otherwise. Returns ``None`` if neither
    yields a valid IP — never raises.
    """
    from django.conf import settings

    remote = (request.META.get("REMOTE_ADDR") or "").strip()
    trusted = getattr(settings, "PIQUANO_TRUSTED_PROXIES", ())

    if remote and trusted and _ip_in_list(remote, trusted):
        forwarded = (request.META.get("HTTP_X_FORWARDED_FOR") or "").split(",")
        for candidate in forwarded:
            candidate = candidate.strip()
            if _is_valid_ip(candidate):
                return candidate

    return remote if _is_valid_ip(remote) else None


def _is_valid_ip(value: str) -> bool:
    try:
        ipaddress.ip_address(value)
        return True
    except (ValueError, TypeError):
        return False


def _ip_in_list(ip: str, candidates: Iterable[str]) -> bool:
    try:
        addr = ipaddress.ip_address(ip)
    except ValueError:
        return False
    for entry in candidates:
        try:
            if "/" in entry:
                if addr in ipaddress.ip_network(entry, strict=False):
                    return True
            elif addr == ipaddress.ip_address(entry):
                return True
        except ValueError:
            continue
    return False


def model_field_names(model: type[models.Model]) -> set[str]:
    """Return the set of concrete field names on a Django model.

    Uses ``_meta.concrete_fields`` so reverse relations and m2m descriptors
    are excluded — important for the DSGVO helpers that key on a literal
    field name like ``email``.
    """
    return {f.name for f in model._meta.concrete_fields}


def models_with_field(
    models_to_scan: Iterable[type[models.Model]], field: str
) -> Iterable[tuple[type[models.Model], set[str]]]:
    """Yield ``(model, field_names)`` for every model that has the given field."""
    for model in models_to_scan:
        names = model_field_names(model)
        if field in names:
            yield model, names
