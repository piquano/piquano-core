"""
Mailjet Send API v3.1 wrapper.

A class-based client + module-level convenience function. Apps that need
template merging or campaign tracking should keep that logic in their own
``emails`` app and use this wrapper for the actual HTTP call.

Settings (read by :meth:`MailjetClient.from_settings`):

* ``MAILJET_API_KEY``      — public Mailjet key (required)
* ``MAILJET_SECRET_KEY``   — private Mailjet key (required)
* ``MAILJET_SENDER``       — verified sender, falls back to ``DEFAULT_FROM_EMAIL``
* ``MAILJET_SENDER_NAME``  — display name (default ``PIQUANO``)
* ``MAILJET_TIMEOUT``      — request timeout seconds (default 30)

The ``MAILJET_*`` prefix matches the existing CRM convention; do not rename.
"""

from __future__ import annotations

import functools
import logging
from dataclasses import dataclass

import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

logger = logging.getLogger(__name__)

MAILJET_SEND_URL = "https://api.mailjet.com/v3.1/send"
DEFAULT_SENDER_NAME = "PIQUANO"
DEFAULT_TIMEOUT = 30


class MailjetError(Exception):
    """Raised when a Mailjet send fails."""


@dataclass(frozen=True)
class MailjetResult:
    """Outcome of a single Mailjet send."""

    success: bool
    message_id: str = ""
    error: str = ""


def _build_session() -> requests.Session:
    session = requests.Session()
    retry = Retry(
        total=2,
        connect=2,
        read=2,
        backoff_factor=0.5,
        status_forcelist=(502, 503, 504),
        allowed_methods=frozenset(["POST"]),
    )
    adapter = HTTPAdapter(max_retries=retry, pool_connections=2, pool_maxsize=4)
    session.mount("https://", adapter)
    return session


# Reuse one TCP+TLS connection across all sends from this process.
_SESSION = _build_session()


class MailjetClient:
    """Stateless Mailjet Send v3.1 client."""

    def __init__(
        self,
        api_key: str,
        secret_key: str,
        sender: str,
        sender_name: str = DEFAULT_SENDER_NAME,
        timeout: int = DEFAULT_TIMEOUT,
    ):
        self.api_key = api_key
        self.secret_key = secret_key
        self.sender = sender
        self.sender_name = sender_name
        self.timeout = timeout

    @classmethod
    @functools.lru_cache(maxsize=1)
    def from_settings(cls) -> MailjetClient:
        from django.conf import settings

        api_key = getattr(settings, "MAILJET_API_KEY", "")
        secret_key = getattr(settings, "MAILJET_SECRET_KEY", "")
        if not api_key or not secret_key:
            raise MailjetError("MAILJET_API_KEY and MAILJET_SECRET_KEY must be set")

        sender = getattr(settings, "MAILJET_SENDER", "") or getattr(
            settings, "DEFAULT_FROM_EMAIL", ""
        )
        if not sender:
            raise MailjetError(
                "Set MAILJET_SENDER or Django's DEFAULT_FROM_EMAIL to a verified address"
            )

        return cls(
            api_key=api_key,
            secret_key=secret_key,
            sender=sender,
            sender_name=getattr(settings, "MAILJET_SENDER_NAME", DEFAULT_SENDER_NAME),
            timeout=getattr(settings, "MAILJET_TIMEOUT", DEFAULT_TIMEOUT),
        )

    def send(
        self,
        to_email: str,
        to_name: str,
        subject: str,
        html_body: str,
        text_body: str | None = None,
        unsubscribe_url: str | None = None,
        custom_id: str | None = None,
        attachments: list[dict] | None = None,
        cc: list[dict] | None = None,
        *,
        log_app: str = "",
        log_type: str = "",
    ) -> MailjetResult:
        """Send a single transactional email.

        Returns a :class:`MailjetResult`. Does not raise — callers log the
        result and decide whether to retry. For exception-style flow use
        :meth:`send_or_raise`.

        ``attachments`` is a list of dicts with keys:
        ``ContentType``, ``Filename``, ``Base64Content``.

        ``cc`` is a list of dicts with keys: ``Email``, ``Name``.
        """
        message: dict = {
            "From": {"Email": self.sender, "Name": self.sender_name},
            "To": [{"Email": to_email, "Name": to_name or to_email}],
            "Subject": subject,
            "HTMLPart": html_body,
        }
        if cc:
            message["Cc"] = cc
        if text_body:
            message["TextPart"] = text_body
        if unsubscribe_url:
            message["Headers"] = {"List-Unsubscribe": f"<{unsubscribe_url}>"}
        if custom_id:
            message["CustomID"] = custom_id
        if attachments:
            message["Attachments"] = attachments

        try:
            resp = _SESSION.post(
                MAILJET_SEND_URL,
                json={"Messages": [message]},
                auth=(self.api_key, self.secret_key),
                timeout=self.timeout,
            )
        except requests.RequestException as exc:
            logger.warning("Mailjet request error: %s", exc)
            result = MailjetResult(success=False, error=str(exc))
            self._log(log_app, log_type, to_email, subject, html_body, result)
            return result

        try:
            data = resp.json()
        except ValueError:
            result = MailjetResult(success=False, error=f"HTTP {resp.status_code}: invalid JSON")
            self._log(log_app, log_type, to_email, subject, html_body, result)
            return result

        if resp.status_code != 200 or not data.get("Messages"):
            result = MailjetResult(success=False, error=f"HTTP {resp.status_code}")
            self._log(log_app, log_type, to_email, subject, html_body, result)
            return result

        msg = data["Messages"][0]
        if msg.get("Status") != "success":
            error = (msg.get("Errors") or [{}])[0].get("ErrorMessage", "Unknown error")
            result = MailjetResult(success=False, error=error)
            self._log(log_app, log_type, to_email, subject, html_body, result)
            return result

        msg_id = str(msg["To"][0]["MessageID"]) if msg.get("To") else ""
        result = MailjetResult(success=True, message_id=msg_id)
        self._log(log_app, log_type, to_email, subject, html_body, result)
        return result

    @staticmethod
    def _log(
        app: str,
        email_type: str,
        recipient: str,
        subject: str,
        body_html: str,
        result: MailjetResult,
    ) -> None:
        if not app or not email_type:
            return
        try:
            from piquano_core.shared.models import EmailLog, EmailLogStatus

            EmailLog.log(
                app=app,
                email_type=email_type,
                recipient=recipient,
                subject=subject,
                status=EmailLogStatus.SENT if result.success else EmailLogStatus.FAILED,
                error_message=result.error,
                body_html=body_html[:50_000] if body_html else "",
                mailjet_message_id=result.message_id,
            )
        except Exception as exc:
            logger.warning("EmailLog failed: %s", exc)

    def send_or_raise(self, **kwargs) -> str:
        """Like :meth:`send` but raises :class:`MailjetError` on failure.

        Returns the Mailjet message ID on success.
        """
        result = self.send(**kwargs)
        if not result.success:
            raise MailjetError(result.error)
        return result.message_id


def send_transactional(*, log_app: str = "", log_type: str = "", **kwargs) -> MailjetResult:
    """Convenience: send via the cached settings-based client."""
    return MailjetClient.from_settings().send(**kwargs, log_app=log_app, log_type=log_type)
