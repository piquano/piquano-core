"""
ATS API client.

Wraps the internal ATS REST endpoints behind a small Python class so
downstream apps (piquano-app, CRM) don't reimplement HTTP plumbing.

Settings (read by :meth:`from_settings`):

* ``PIQUANO_ATS_BASE_URL``    — e.g. ``https://ats.piquano.com``
* ``PIQUANO_ATS_API_TOKEN``   — bearer token issued by the ATS
* ``PIQUANO_ATS_TIMEOUT``     — request timeout in seconds (default 10)
* ``PIQUANO_ATS_CACHE_TTL``   — read-cache TTL in seconds (default 60)

Usage::

    from piquano_core.ats_client import ATSClient
    ats = ATSClient.from_settings()
    candidate = ats.get_candidate("some-uuid")
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
DEFAULT_CACHE_TTL = 60
RETRY_STATUSES = (502, 503, 504)


class ATSClientError(Exception):
    """Raised when an ATS API call fails."""


class ATSClientNotFound(ATSClientError):
    """Raised when an ATS lookup returns 404."""


class ATSClient:
    """Thin REST client for the internal ATS API."""

    def __init__(
        self,
        base_url: str,
        api_token: str,
        timeout: int = DEFAULT_TIMEOUT,
        cache_ttl: int = DEFAULT_CACHE_TTL,
    ):
        self.base_url = base_url.rstrip("/") + "/"
        self.api_token = api_token
        self.timeout = timeout
        self._session = self._build_session()
        # Re-use the TTL cache from crm_client — same pattern.
        from piquano_core.crm_client.client import _TTLCache

        self._cache = _TTLCache(cache_ttl) if cache_ttl > 0 else None

    def _build_session(self) -> requests.Session:
        session = requests.Session()
        session.headers.update(
            {
                "Authorization": f"Token {self.api_token}",
                "Accept": "application/json",
                "User-Agent": "piquano-core/0.7.0",
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
    def from_settings(cls) -> ATSClient:
        """Build (and cache) a client from Django settings."""
        from django.conf import settings

        base_url = getattr(settings, "PIQUANO_ATS_BASE_URL", "")
        token = getattr(settings, "PIQUANO_ATS_API_TOKEN", "")
        timeout = getattr(settings, "PIQUANO_ATS_TIMEOUT", DEFAULT_TIMEOUT)
        cache_ttl = getattr(settings, "PIQUANO_ATS_CACHE_TTL", DEFAULT_CACHE_TTL)
        if not base_url or not token:
            raise ATSClientError("PIQUANO_ATS_BASE_URL and PIQUANO_ATS_API_TOKEN must be set")
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
            logger.warning("ATS API %s %s failed: %s", method, path, exc)
            raise ATSClientError(str(exc)) from exc

        if resp.status_code == 404:
            raise ATSClientNotFound(f"Not found: {method} {path}")

        if resp.status_code >= 400:
            logger.warning("ATS API %s %s -> %s", method, path, resp.status_code)
            raise ATSClientError(f"HTTP {resp.status_code} on {method} {path}")

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
        if self._cache is None:
            return
        if key is None:
            self._cache.clear()
        else:
            self._cache.invalidate(key)

    # ----- candidates ---------------------------------------------------------

    def get_candidate(self, candidate_id: str) -> dict:
        """Fetch a single candidate by UUID."""
        return self._request(
            "GET",
            f"api/v1/candidates/{candidate_id}/",
            cache_key=f"candidate:{candidate_id}",
        )

    def get_candidate_by_public_id(self, public_id: str) -> dict:
        """Fetch a single candidate by menschenlesbarer UID (z.B. A0000042)."""
        uid = (public_id or "").strip().upper()
        if not uid:
            raise ATSClientError("public_id must be non-empty")
        return self._request(
            "GET",
            f"api/v1/candidates/by-uid/{uid}/",
            cache_key=f"candidate_uid:{uid}",
        )

    def search_candidates(self, query: str, limit: int = 25) -> list[dict]:
        """Search candidates by name or email."""
        data = self._request(
            "GET", "api/v1/candidates/", params={"search": query, "page_size": limit}
        )
        if not isinstance(data, dict) or "results" not in data:
            raise ATSClientError("unexpected response shape from /api/v1/candidates/")
        return data["results"]

    # ----- jobs ---------------------------------------------------------------

    def get_job(self, job_id: str) -> dict:
        """Fetch a single job by UUID."""
        return self._request(
            "GET",
            f"api/v1/jobs/{job_id}/",
            cache_key=f"job:{job_id}",
        )

    def list_jobs(self, status: str | None = None, limit: int = 25) -> list[dict]:
        """List jobs, optionally filtered by status."""
        params: dict[str, Any] = {"page_size": limit}
        if status:
            params["status"] = status
        data = self._request("GET", "api/v1/jobs/", params=params)
        if not isinstance(data, dict) or "results" not in data:
            raise ATSClientError("unexpected response shape from /api/v1/jobs/")
        return data["results"]

    # ----- applications --------------------------------------------------------

    def get_job_applications(self, job_id: str) -> list[dict]:
        """Fetch all applications for a given job, including candidate and stage."""
        data = self._request(
            "GET",
            "api/v1/applications/",
            params={"job": job_id, "page_size": 100},
            cache_key=f"job_applications:{job_id}",
        )
        if not isinstance(data, dict) or "results" not in data:
            raise ATSClientError("unexpected response shape from /api/v1/applications/")
        return data["results"]

    # ----- health -------------------------------------------------------------

    def health(self) -> bool:
        """Lightweight liveness probe."""
        try:
            self._request("GET", "api/v1/candidates/", params={"page_size": 1})
            return True
        except ATSClientError:
            return False
