"""
Persönlicher E-Mail-Versand über MS Graph API.

Zentrale Funktion für ATS + CRM: sendet über das Outlook-Postfach
des Users (erscheint in "Gesendete Objekte"). Kein Fallback auf Mailjet —
User muss Postfach verbunden haben.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

logger = logging.getLogger(__name__)


class MailAccountNotConnected(Exception):
    """User hat kein MS365-Postfach verbunden."""

    pass


class MailAccountNeedsReauth(Exception):
    """Outlook-Verbindung abgelaufen, User muss neu verbinden."""

    pass


@dataclass
class SendResult:
    ok: bool
    graph_message_id: str = ""
    internet_message_id: str = ""
    conversation_id: str = ""
    error: str = ""


def _get_mail_account(user_email: str):
    """MailAccount für eine E-Mail-Adresse finden.

    Versucht zuerst das lokale ORM-Model (CRM), dann die Bridge (ATS/App).
    """
    # Versuch 1: lokales MailAccount-Model (CRM hat es direkt)
    try:
        from .models import MailAccount

        account = MailAccount.objects.filter(upn__iexact=user_email).first()
        if account:
            return account
    except Exception:
        pass

    # Versuch 2: Bridge (ATS und andere Apps)
    try:
        from .bridge import get_connected_accounts

        for account in get_connected_accounts():
            if account.upn.lower() == user_email.lower():
                return account
    except Exception as exc:
        logger.warning("Bridge-Lookup für %s fehlgeschlagen: %s", user_email, exc)

    return None


def check_mail_account(user_email: str) -> None:
    """Prüft ob ein MailAccount verbunden ist. Wirft Exception wenn nicht.

    Nützlich für Vorab-Check vor Schleifen (Sammel-Mail).
    """
    account = _get_mail_account(user_email)
    if not account:
        raise MailAccountNotConnected(
            "Bitte zuerst dein Outlook-Postfach verbinden."
        )
    if getattr(account, "status", "") == "needs_reauth":
        raise MailAccountNeedsReauth(
            "Deine Outlook-Verbindung ist abgelaufen. "
            "Bitte neu verbinden, damit E-Mails über dein Postfach gesendet werden können."
        )


def send_personal_email(
    *,
    user_email: str,
    to_email: str,
    to_name: str = "",
    subject: str,
    body_html: str,
    body_text: str = "",
    cc: list[str] | None = None,
    bcc: list[str] | None = None,
) -> SendResult:
    """Sendet eine persönliche E-Mail über MS Graph (Outlook des Users).

    Raises:
        MailAccountNotConnected: Kein Postfach verbunden
        MailAccountNeedsReauth: Token abgelaufen
    """
    account = _get_mail_account(user_email)

    if not account:
        raise MailAccountNotConnected(
            "Bitte zuerst dein Outlook-Postfach verbinden."
        )

    if getattr(account, "status", "") == "needs_reauth":
        raise MailAccountNeedsReauth(
            "Deine Outlook-Verbindung ist abgelaufen. "
            "Bitte neu verbinden, damit E-Mails über dein Postfach gesendet werden können."
        )

    from .graph import GraphClient, GraphError, TokenInvalidError

    client = GraphClient(account)

    try:
        draft = client.create_and_send_draft(
            to=[to_email],
            subject=subject,
            body_html=body_html,
            cc=cc,
            bcc=bcc,
        )
        return SendResult(
            ok=True,
            graph_message_id=draft.get("id", ""),
            internet_message_id=draft.get("internetMessageId", ""),
            conversation_id=draft.get("conversationId", ""),
        )
    except TokenInvalidError as exc:
        raise MailAccountNeedsReauth(
            "Deine Outlook-Verbindung ist abgelaufen. "
            "Bitte neu verbinden, damit E-Mails über dein Postfach gesendet werden können."
        ) from exc
    except GraphError as exc:
        logger.error("Graph-Versand fehlgeschlagen für %s: %s", user_email, exc)
        return SendResult(ok=False, error=str(exc))
