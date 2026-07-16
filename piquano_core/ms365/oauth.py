"""OAuth-Flow-Helper für Microsoft Identity Platform (v2.0)."""

from __future__ import annotations

import logging
import secrets

import msal
from django.conf import settings
from django.urls import reverse

logger = logging.getLogger(__name__)

SCOPES = [
    "Mail.Read",
    "Mail.Send",
    "Mail.ReadWrite",
    "User.Read",
    "Files.Read.All",
    "Sites.Read.All",
]

AUTHORITY_TEMPLATE = "https://login.microsoftonline.com/{tenant}"


def _client() -> msal.ConfidentialClientApplication:
    return msal.ConfidentialClientApplication(
        client_id=settings.MS365_CLIENT_ID,
        client_credential=settings.MS365_CLIENT_SECRET,
        authority=AUTHORITY_TEMPLATE.format(tenant=settings.MS365_TENANT_ID or "common"),
    )


def build_redirect_uri(request) -> str:
    if getattr(settings, "MS365_REDIRECT_URI", ""):
        return settings.MS365_REDIRECT_URI
    return request.build_absolute_uri(reverse("piquano_ms365:callback"))


def start_flow(request) -> tuple[str, dict]:
    flow = _client().initiate_auth_code_flow(
        scopes=SCOPES,
        redirect_uri=build_redirect_uri(request),
        state=secrets.token_urlsafe(24),
        prompt="select_account",
        response_mode="form_post",
    )
    return flow["auth_uri"], flow


def complete_flow(request, flow: dict, query_params: dict) -> dict:
    result = _client().acquire_token_by_auth_code_flow(flow, query_params)
    if "error" in result:
        logger.error("MS365 OAuth-Fehler: %s", result)
        raise RuntimeError(f"OAuth-Fehler: {result.get('error_description') or result['error']}")
    return result


def refresh_access_token(refresh_token: str) -> dict:
    result = _client().acquire_token_by_refresh_token(refresh_token, scopes=SCOPES)
    if "error" in result:
        logger.warning("MS365 Token-Refresh-Fehler: %s", result)
        raise RuntimeError(
            f"Token-Refresh fehlgeschlagen: {result.get('error_description') or result['error']}"
        )
    return result
