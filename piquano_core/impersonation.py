"""
Cross-App User-Impersonation fuer Admins.

Verwendet einen signierten Cookie auf .piquano.com, damit die
Impersonation ueber alle Piquano-Apps hinweg funktioniert.

Die Signierung nutzt PIQUANO_IMPERSONATION_KEY (identisch in allen Apps),
NICHT den app-spezifischen SECRET_KEY.

Middleware-Reihenfolge: NACH PiquanoPermissionMiddleware, damit
der echte Admin zuerst authentifiziert wird.

Sicherheit:
- Nur Authelia-Admins koennen impersonieren
- Cookie ist kryptografisch signiert (HMAC mit shared Key)
- Audit-Logging bei Start und Stop
- Cookie-Max-Age: 8 Stunden
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import json
import logging
import os
import time

from django.conf import settings
from django.contrib.auth import get_user_model

logger = logging.getLogger(__name__)

COOKIE_NAME = "pq_impersonate"
COOKIE_MAX_AGE = 8 * 3600  # 8 Stunden


def _get_shared_key():
    """Shared Key fuer Cookie-Signierung (identisch in allen Apps).

    Liest direkt aus os.environ, damit es unabhaengig von app-spezifischen
    Django-Settings funktioniert. Alle Apps laden .env via dotenv.
    """
    key = os.environ.get("PIQUANO_IMPERSONATION_KEY", "")
    if not key:
        raise ValueError("PIQUANO_IMPERSONATION_KEY muss in .env gesetzt sein")
    return key.encode()


def _sign(payload: str) -> str:
    """HMAC-SHA256 Signatur erstellen."""
    return hmac.new(_get_shared_key(), payload.encode(), hashlib.sha256).hexdigest()


def get_cookie_domain():
    """Cookie-Domain aus Settings oder Default."""
    return getattr(settings, "PIQUANO_COOKIE_DOMAIN", ".piquano.com")


def set_impersonation_cookie(response, target_username, real_username):
    """Signierten Impersonation-Cookie setzen."""
    payload = json.dumps({
        "target": target_username,
        "real": real_username,
        "ts": int(time.time()),
    }, separators=(",", ":"))
    sig = _sign(payload)
    # Base64-Kodierung: Cookie-safe (keine Quotes, Spaces, Sonderzeichen)
    b64 = base64.urlsafe_b64encode(payload.encode()).decode()
    value = f"{b64}.{sig}"
    response.set_cookie(
        COOKIE_NAME,
        value,
        max_age=COOKIE_MAX_AGE,
        domain=get_cookie_domain(),
        httponly=True,
        secure=True,
        samesite="Lax",
    )


def clear_impersonation_cookie(response):
    """Impersonation-Cookie loeschen."""
    response.delete_cookie(
        COOKIE_NAME,
        domain=get_cookie_domain(),
    )


def read_impersonation_cookie(request):
    """Cookie lesen und verifizieren. Gibt (target, real) oder (None, None) zurueck."""
    raw = request.COOKIES.get(COOKIE_NAME)
    if not raw:
        return None, None
    try:
        parts = raw.rsplit(".", 1)
        if len(parts) != 2:
            return None, None
        b64, sig = parts
        payload = base64.urlsafe_b64decode(b64.encode()).decode()
        expected_sig = _sign(payload)
        if not hmac.compare_digest(sig, expected_sig):
            logger.warning("Impersonation cookie: ungueltige Signatur")
            return None, None
        data = json.loads(payload)
        # Zeitpruefung
        ts = data.get("ts", 0)
        if time.time() - ts > COOKIE_MAX_AGE:
            return None, None
        return data.get("target"), data.get("real")
    except (ValueError, KeyError, json.JSONDecodeError):
        return None, None


class ImpersonationMiddleware:
    """Tauscht request.user wenn ein Impersonation-Cookie aktiv ist.

    Muss NACH PiquanoPermissionMiddleware laufen, damit der echte Admin
    zuerst authentifiziert wird. Danach wird request.user getauscht und
    die Permissions fuer den Ziel-User neu geladen.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        target_username, real_username = read_impersonation_cookie(request)

        if target_username and request.user.is_authenticated:
            # Sicherstellen, dass der echte User noch Admin ist
            admin_group = getattr(settings, "PIQUANO_AUTH_ADMIN_GROUP", "admins")
            groups_raw = request.META.get("HTTP_REMOTE_GROUPS", "")
            groups = {g.strip() for g in groups_raw.split(",") if g.strip()}

            if admin_group not in groups:
                request.is_impersonating = False
                request.real_user = request.user
                response = self.get_response(request)
                clear_impersonation_cookie(response)
                return response

            User = get_user_model()
            target_user = self._get_or_provision_user(User, target_username)
            if target_user is None:
                request.is_impersonating = False
                request.real_user = request.user
                response = self.get_response(request)
                clear_impersonation_cookie(response)
                return response

            # CRM-Daten laden (team_id wird nur in-memory gesetzt)
            self._enrich_from_crm(target_user, target_username)

            # Echten User merken, Ziel-User einsetzen
            request.real_user = request.user
            request.is_impersonating = True
            request.user = target_user

            # Permissions neu laden fuer den Ziel-User
            from piquano_core.admin_center.middleware import (
                _check_perm,
                _check_toggle,
            )

            target_user._piquano_is_admin = False
            target_user._piquano_perms = None
            target_user._piquano_toggles = None
            target_user.has_piquano_perm = lambda codename: _check_perm(
                target_user, codename
            )
            target_user.is_feature_enabled = lambda app, module: _check_toggle(
                target_user, app, module
            )
        else:
            request.is_impersonating = False
            request.real_user = request.user

        return self.get_response(request)

    def _get_or_provision_user(self, User, username):
        """User lokal laden oder aus CRM auto-provisionieren."""
        try:
            return User.objects.get(username=username, is_active=True)
        except User.DoesNotExist:
            pass

        # User existiert lokal nicht — aus CRM anlegen
        try:
            from piquano_core.crm_client import CRMClient, CRMClientError

            client = CRMClient.from_settings()
            data = client.get_user(username)
            user = User.objects.create(
                username=username,
                first_name=data.get("first_name", ""),
                last_name=data.get("last_name", ""),
                email=data.get("email", ""),
                is_active=True,
            )
            user.set_unusable_password()
            user.save(update_fields=["password"])
            logger.info("Impersonation: User %s lokal provisioniert", username)
            return user
        except CRMClientError:
            logger.warning("Impersonation: CRM nicht erreichbar fuer %s", username)
            return None
        except Exception:
            logger.warning("Impersonation: User %s konnte nicht angelegt werden", username)
            return None

    def _enrich_from_crm(self, user, username):
        """team_id und Profilfelder aus CRM laden (in-memory)."""
        try:
            from piquano_core.crm_client import CRMClient, CRMClientError

            client = CRMClient.from_settings()
            data = client.get_user(username)

            # team_id setzen (nicht persisted, nur in-memory)
            team_data = data.get("team")
            if isinstance(team_data, dict) and team_data.get("id"):
                user.team_id = team_data["id"]

            # Profilfelder aktualisieren (in-memory)
            for field in ("first_name", "last_name", "email"):
                val = data.get(field)
                if val:
                    setattr(user, field, val)
            for field in ("phone", "avatar_url"):
                if hasattr(user, field):
                    val = data.get(field)
                    if val:
                        setattr(user, field, val)

            # Privacy-Version (in-memory, fuer Banner-Check)
            user._privacy_version = data.get("privacy_version") or ""
            user._privacy_accepted_at = data.get("privacy_accepted_at") or ""
        except Exception:
            logger.debug("Impersonation: CRM-Enrich fuer %s fehlgeschlagen", username)
