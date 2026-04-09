"""
CRM API client.

Wraps the internal CRM REST endpoints behind a small Python class so
downstream apps (ATS, Ticket, LMS, the new piquano-app) don't reimplement
HTTP plumbing, auth headers, or retry logic.

Endpoints implemented as of v0.2.0:

* ``get_user(username)`` — Phase 0.J.7 user-detail endpoint
* ``list_users(...)`` — paginated user list
* Stubs for contact/company endpoints (still WIP, see Phase 0.C)

Settings (read by :meth:`from_settings`):

* ``PIQUANO_CRM_BASE_URL``    — e.g. ``https://crm.piquano.com``
* ``PIQUANO_CRM_API_TOKEN``   — bearer token issued by the CRM
* ``PIQUANO_CRM_TIMEOUT``     — request timeout in seconds (default 10)
* ``PIQUANO_CRM_CACHE_TTL``   — read-cache TTL in seconds (default 60)

Usage::

    from piquano_core.crm_client import CRMClient
    crm = CRMClient.from_settings()  # cached singleton
    user = crm.get_user("alice")     # cached for ``cache_ttl`` seconds
"""

from __future__ import annotations

import functools
import logging
import time
from typing import Any
from urllib.parse import urljoin

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

DEFAULT_TIMEOUT = 10
DEFAULT_CACHE_TTL = 60
RETRY_STATUSES = (502, 503, 504)


class CRMClientError(Exception):
    """Raised when a CRM API call fails."""


class CRMClientNotFound(CRMClientError):
    """Raised when a CRM lookup returns 404."""


class _TTLCache:
    """Tiny in-process TTL cache used by CRMClient.

    Not thread-safe in the strict sense — Python dict ops are atomic enough
    for the per-request access pattern in Django views, and stale reads
    during a race are acceptable for user-profile data.
    """

    def __init__(self, ttl: int):
        self.ttl = ttl
        self._store: dict[str, tuple[float, Any]] = {}

    def get(self, key: str) -> Any | None:
        entry = self._store.get(key)
        if entry is None:
            return None
        expires_at, value = entry
        if time.monotonic() >= expires_at:
            self._store.pop(key, None)
            return None
        return value

    def set(self, key: str, value: Any) -> None:
        self._store[key] = (time.monotonic() + self.ttl, value)

    def invalidate(self, key: str) -> None:
        self._store.pop(key, None)

    def clear(self) -> None:
        self._store.clear()


class CRMClient:
    """Thin REST client for the internal CRM API."""

    def __init__(
        self,
        base_url: str,
        api_token: str,
        timeout: int = DEFAULT_TIMEOUT,
        cache_ttl: int = DEFAULT_CACHE_TTL,
    ):
        # Trailing slash matters for urljoin: "https://x/api" + "contacts/" -> "https://x/contacts/"
        # whereas "https://x/api/" + "contacts/" -> "https://x/api/contacts/".
        self.base_url = base_url.rstrip("/") + "/"
        self.api_token = api_token
        self.timeout = timeout
        self._session = self._build_session()
        self._cache = _TTLCache(cache_ttl) if cache_ttl > 0 else None

    def _build_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update(
            {
                "Authorization": f"Token {self.api_token}",
                "Accept": "application/json",
                "User-Agent": "piquano-core/0.6.0",
            }
        )
        retry = Retry(
            total=2,
            connect=2,
            read=2,
            backoff_factor=0.3,
            status_forcelist=RETRY_STATUSES,
            # POST wird nicht retried — Timeline-Push ist best-effort,
            # Retry würde bei transienten 5xx Duplikate erzeugen.
            allowed_methods=frozenset(["GET", "HEAD"]),
        )
        adapter = HTTPAdapter(max_retries=retry, pool_connections=4, pool_maxsize=8)
        session.mount("https://", adapter)
        session.mount("http://", adapter)
        return session

    @classmethod
    @functools.lru_cache(maxsize=1)
    def from_settings(cls) -> CRMClient:
        """Build (and cache) a client from Django settings."""
        from django.conf import settings

        base_url = getattr(settings, "PIQUANO_CRM_BASE_URL", "")
        token = getattr(settings, "PIQUANO_CRM_API_TOKEN", "")
        timeout = getattr(settings, "PIQUANO_CRM_TIMEOUT", DEFAULT_TIMEOUT)
        cache_ttl = getattr(settings, "PIQUANO_CRM_CACHE_TTL", DEFAULT_CACHE_TTL)
        if not base_url or not token:
            raise CRMClientError("PIQUANO_CRM_BASE_URL and PIQUANO_CRM_API_TOKEN must be set")
        return cls(
            base_url=base_url,
            api_token=token,
            timeout=timeout,
            cache_ttl=cache_ttl,
        )

    # ----- low-level ----------------------------------------------------------

    def _request(
        self,
        method: str,
        path: str,
        *,
        params: dict | None = None,
        json: dict | None = None,
        cache_key: str | None = None,
    ) -> Any:
        if method == "GET" and self._cache is not None and cache_key is not None:
            cached = self._cache.get(cache_key)
            if cached is not None:
                return cached

        url = urljoin(self.base_url, path.lstrip("/"))
        try:
            resp = self._session.request(
                method, url, params=params, json=json, timeout=self.timeout
            )
        except requests.RequestException as exc:
            logger.warning("CRM API %s %s failed: %s", method, path, exc)
            raise CRMClientError(str(exc)) from exc

        if resp.status_code == 404:
            logger.info("CRM API %s %s -> 404", method, path)
            raise CRMClientNotFound(f"Not found: {method} {path}")

        if resp.status_code >= 400:
            # Don't log the body — CRM responses can contain contact PII.
            logger.warning("CRM API %s %s -> %s", method, path, resp.status_code)
            raise CRMClientError(f"HTTP {resp.status_code} on {method} {path}")

        data = None if resp.status_code == 204 or not resp.content else resp.json()

        if (
            method == "GET"
            and self._cache is not None
            and cache_key is not None
            and data is not None
        ):
            self._cache.set(cache_key, data)

        return data

    def invalidate_cache(self, key: str | None = None) -> None:
        """Invalidate one cached entry or the whole cache."""
        if self._cache is None:
            return
        if key is None:
            self._cache.clear()
        else:
            self._cache.invalidate(key)

    # ----- users (Phase 0.J.7) ------------------------------------------------

    def get_user(self, username: str) -> dict:
        """Fetch a single user by username. Raises :class:`CRMClientNotFound`."""
        username = username.strip()
        if not username:
            raise CRMClientError("username must be non-empty")
        return self._request(
            "GET",
            f"api/users/{username}/",
            cache_key=f"user:{username}",
        )

    def list_users(self, q: str | None = None, limit: int = 50) -> list[dict]:
        """Search/list users. Returns the ``results`` array of a paginated response."""
        params: dict[str, Any] = {"page_size": limit}
        if q:
            params["search"] = q
        data = self._request("GET", "api/users/", params=params)
        if not isinstance(data, dict) or "results" not in data:
            raise CRMClientError("unexpected response shape from /api/users/")
        return data["results"]

    # ----- contacts (stubs — Phase 0.C will harden these) ---------------------

    def get_contact(self, contact_id: int) -> dict:
        """Fetch a single contact by ID."""
        return self._request("GET", f"api/contacts/{contact_id}/")

    def search_contacts(self, query: str, limit: int = 20) -> list[dict]:
        """Search contacts by name, email, or company."""
        data = self._request("GET", "api/contacts/", params={"search": query, "page_size": limit})
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
            self._request("GET", "api/users/", params={"page_size": 1})
            return True
        except CRMClientError:
            return False

    # ----- timeline events (v0.6.0) -------------------------------------------

    def post_event(
        self,
        *,
        source_app: str,
        actor_username: str,
        verb: str,
        target_type: str = "",
        target_id: str = "",
        target_label: str = "",
        target_url: str = "",
        summary: str = "",
        extra: dict | None = None,
        occurred_at: str | None = None,
    ) -> dict | None:
        """Push einen Cross-App-Event an die CRM-Timeline.

        **Fire-and-forget**: alle Fehler werden gefangen und als Warning
        geloggt. Niemals raisen — der Caller soll durch einen CRM-Ausfall
        nicht blockiert oder ausgebremst werden.

        Gibt die Antwort des CRM zurück (dict) wenn erfolgreich, sonst None.

        Args:
            source_app: Name der Origin-App (``piquano-app``, ``ats``, …)
            actor_username: Authelia-Username des Users der die Aktion
                ausgeführt hat
            verb: eins der :class:`TimelineVerb`-Labels (create, update,
                publish, notify, sync, generate, delete, unpublish)
            target_type: Model-Name im Origin-System (``casestudy``, …)
            target_id: Primary Key des Targets als String
            target_label: Menschenlesbare Beschriftung
            target_url: Deep-Link zurück ins Origin-System
            summary: kurzer Human-Readable-Text
            extra: dict mit zusätzlichen strukturierten Daten
            occurred_at: ISO-8601 Zeitstempel wann die Aktion passiert ist;
                wenn None wird der aktuelle Zeitpunkt benutzt
        """
        from datetime import datetime, timezone

        payload = {
            "source_app": source_app,
            "actor_username": actor_username or "",
            "verb": verb,
            "target_type": target_type or "",
            "target_id": str(target_id) if target_id else "",
            "target_label": (target_label or "")[:500],
            "target_url": target_url or "",
            "summary": (summary or "")[:500],
            "extra": extra or {},
            "occurred_at": occurred_at or datetime.now(timezone.utc).isoformat(),
        }

        try:
            return self._request("POST", "api/timeline/events/", json=payload)
        except CRMClientError as exc:
            logger.warning(
                "post_event fire-and-forget failed (verb=%s target=%s/%s): %s",
                verb,
                target_type,
                target_id,
                exc,
            )
            return None
