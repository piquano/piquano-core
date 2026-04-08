"""
CRM API client.

Wraps the internal CRM REST endpoints behind a small Python class so
downstream apps (ATS, Ticket, LMS) don't reimplement HTTP plumbing,
auth headers, or retry logic.

The high-level methods below are stubs — the CRM API surface is being
hardened in Phase 0.C of the platform-extension plan. Method bodies stay
minimal until the endpoints exist; the *interface* is what consumers
should code against.

Settings (read by :meth:`from_settings`):

* ``PIQUANO_CRM_BASE_URL`` — e.g. ``https://crm.piquano.com``
* ``PIQUANO_CRM_API_TOKEN`` — bearer token issued by the CRM
* ``PIQUANO_CRM_TIMEOUT`` — request timeout in seconds (default 10)

Usage::

    from piquano_core.crm_client import CRMClient
    crm = CRMClient.from_settings()  # cached singleton
    contact = crm.get_contact(42)
"""
from __future__ import annotations

import functools
import logging
from typing import Any
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 10
RETRY_STATUSES = (502, 503, 504)


class CRMClientError(Exception):
    """Raised when a CRM API call fails."""


class CRMClient:
    """Thin REST client for the internal CRM API."""

    def __init__(self, base_url: str, api_token: str, timeout: int = DEFAULT_TIMEOUT):
        # Trailing slash matters for urljoin: "https://x/api" + "contacts/" -> "https://x/contacts/"
        # whereas "https://x/api/" + "contacts/" -> "https://x/api/contacts/".
        self.base_url = base_url.rstrip("/") + "/"
        self.api_token = api_token
        self.timeout = timeout
        self._session = self._build_session()

    def _build_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update(
            {
                "Authorization": f"Bearer {self.api_token}",
                "Accept": "application/json",
                "User-Agent": "piquano-core/0.1.0",
            }
        )
        retry = Retry(
            total=2,
            connect=2,
            read=2,
            backoff_factor=0.3,
            status_forcelist=RETRY_STATUSES,
            allowed_methods=frozenset(["GET", "HEAD"]),
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=4, pool_maxsize=8)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    @classmethod
    @functools.lru_cache(maxsize=1)
    def from_settings(cls) -> "CRMClient":
        """Build (and cache) a client from Django settings."""
        from django.conf import settings

        base_url = getattr(settings, "PIQUANO_CRM_BASE_URL", "")
        token = getattr(settings, "PIQUANO_CRM_API_TOKEN", "")
        timeout = getattr(settings, "PIQUANO_CRM_TIMEOUT", DEFAULT_TIMEOUT)
        if not base_url or not token:
            raise CRMClientError(
                "PIQUANO_CRM_BASE_URL and PIQUANO_CRM_API_TOKEN must be set"
            )
        return cls(base_url=base_url, api_token=token, timeout=timeout)

    # ----- low-level ----------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json: dict | None = None,
    ) -> Any:
        url = urljoin(self.base_url, path.lstrip("/"))
        try:
            resp = self._session.request(
                method, url, params=params, json=json, timeout=self.timeout
            )
        except requests.RequestException as exc:
            logger.warning("CRM API %s %s failed: %s", method, path, exc)
            raise CRMClientError(str(exc)) from exc

        if resp.status_code >= 400:
            # Don't log the body — CRM responses can contain contact PII.
            logger.warning("CRM API %s %s -> %s", method, path, resp.status_code)
            raise CRMClientError(f"HTTP {resp.status_code} on {method} {path}")

        if resp.status_code == 204 or not resp.content:
            return None
        return resp.json()

    # ----- high-level (stubs) -------------------------------------------------

    def get_contact(self, contact_id: int) -> dict:
        """Fetch a single contact by ID."""
        return self._request("GET", f"api/contacts/{contact_id}/")

    def search_contacts(self, query: str, limit: int = 20) -> list[dict]:
        """Search contacts by name, email, or company.

        Expects a paginated DRF response (``{"results": [...]}``). Raises
        :class:`CRMClientError` if the response shape is unexpected — silent
        fall-throughs hide API contract drift.
        """
        data = self._request("GET", "api/contacts/", params={"q": query, "limit": limit})
        if not isinstance(data, dict) or "results" not in data:
            raise CRMClientError("unexpected response shape from /api/contacts/")
        return data["results"]

    def create_contact(self, payload: dict) -> dict:
        """Create a new contact."""
        return self._request("POST", "api/contacts/", json=payload)

    def get_company(self, company_id: int) -> dict:
        return self._request("GET", f"api/companies/{company_id}/")

    def health(self) -> bool:
        """Lightweight liveness probe."""
        try:
            self._request("GET", "api/health/")
            return True
        except CRMClientError:
            return False
