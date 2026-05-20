"""
AdminCenterClient — spricht die Admin-Center-API jeder Piquano-App an.

Konfiguration ueber PIQUANO_APPS dict in Django Settings:

    PIQUANO_APPS = {
        "crm": {"url": "http://127.0.0.1:5003", "token": "...", "label": "CRM"},
        "ats": {"url": "http://127.0.0.1:5006", "token": "...", "label": "ATS"},
        ...
    }

Usage:
    from piquano_core.admin_center.app_client import AdminCenterClient
    clients = AdminCenterClient.all_from_settings()
    for app_label, client in clients.items():
        stats = client.get_stats()
"""

from __future__ import annotations

import logging

import requests

logger = logging.getLogger(__name__)

TIMEOUT = 8


class AdminCenterClientError(Exception):
    pass


class AdminCenterClient:
    """Client fuer die Admin-Center-API einer einzelnen Piquano-App."""

    def __init__(self, app_label: str, base_url: str, api_token: str, label: str = ""):
        self.app_label = app_label
        self.base_url = base_url.rstrip("/")
        self.api_token = api_token
        self.label = label or app_label.upper()
        self._session = requests.Session()
        self._session.headers.update({
            "Authorization": f"Token {self.api_token}",
            "Accept": "application/json",
            "X-Forwarded-Proto": "https",
            "Host": "localhost",
        })

    def _url(self, path: str) -> str:
        return f"{self.base_url}/admin-center/api/{path.lstrip('/')}"

    def _get(self, path: str) -> dict:
        try:
            resp = self._session.get(self._url(path), timeout=TIMEOUT)
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.warning("AdminCenterClient %s GET %s failed: %s", self.app_label, path, e)
            raise AdminCenterClientError(f"{self.app_label}: {e}") from e

    def _post(self, path: str, data: dict) -> dict:
        try:
            resp = self._session.post(
                self._url(path), json=data, timeout=TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.warning("AdminCenterClient %s POST %s failed: %s", self.app_label, path, e)
            raise AdminCenterClientError(f"{self.app_label}: {e}") from e

    def _put(self, path: str, data: dict) -> dict:
        try:
            resp = self._session.put(
                self._url(path), json=data, timeout=TIMEOUT,
            )
            resp.raise_for_status()
            return resp.json()
        except requests.RequestException as e:
            logger.warning("AdminCenterClient %s PUT %s failed: %s", self.app_label, path, e)
            raise AdminCenterClientError(f"{self.app_label}: {e}") from e

    # -- Stats --
    def get_stats(self) -> dict:
        return self._get("stats/")

    # -- Permissions --
    def get_permissions(self) -> list[dict]:
        return self._get("permissions/").get("permissions", [])

    # -- Toggles --
    def get_toggles(self) -> list[dict]:
        return self._get("toggles/").get("toggles", [])

    def set_toggle(self, pk: str, is_enabled: bool) -> dict:
        return self._put(f"toggles/{pk}/", {"is_enabled": is_enabled})

    # -- Users --
    def get_users(self) -> list[dict]:
        return self._get("users/").get("users", [])

    def provision_user(self, username: str, **fields) -> dict:
        """Provision a user in this app's local database.

        Accepts optional fields: first_name, last_name, email, is_staff, is_active.
        Idempotent — safe to call multiple times for the same user.
        """
        return self._post("provision-user/", {"username": username, **fields})

    # -- User Permissions --
    def get_user_permissions(self, username: str, team_id: str = "") -> dict:
        path = f"user-permissions/{username}/"
        if team_id:
            path += f"?team_id={team_id}"
        return self._get(path)

    def save_user_permissions(self, username: str, granted_ids: list[str], team_id: str = "") -> dict:
        path = f"user-permissions/{username}/save/"
        if team_id:
            path += f"?team_id={team_id}"
        return self._put(path, {"granted_ids": granted_ids})

    # -- Team Permissions --
    def get_team_permissions(self, team_id: str) -> dict:
        return self._get(f"team-permissions/{team_id}/")

    def save_team_permissions(self, team_id: str, granted_ids: list[str]) -> dict:
        return self._put(f"team-permissions/{team_id}/save/", {"granted_ids": granted_ids})

    # -- Factory --
    @classmethod
    def all_from_settings(cls) -> dict[str, AdminCenterClient]:
        """Build clients for all apps configured in PIQUANO_APPS."""
        from django.conf import settings
        apps_config = getattr(settings, "PIQUANO_APPS", {})
        clients = {}
        for app_label, cfg in apps_config.items():
            url = cfg.get("url", "")
            token = cfg.get("token", "")
            if url and token:
                clients[app_label] = cls(
                    app_label=app_label,
                    base_url=url,
                    api_token=token,
                    label=cfg.get("label", app_label),
                )
            else:
                logger.warning("PIQUANO_APPS[%s] missing url or token, skipped", app_label)
        return clients

    def __repr__(self):
        return f"AdminCenterClient({self.app_label!r}, {self.base_url!r})"
