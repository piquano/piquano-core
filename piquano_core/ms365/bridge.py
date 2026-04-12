"""
Cross-DB Bridge: liest MailAccount-Daten aus der CRM-Datenbank.

Alle Apps außer dem CRM nutzen diesen Bridge statt eigener MailAccount-Models.
Der CRM ist Master für OAuth-Tokens — hier wird nur gelesen und bei
Token-Refresh zurückgeschrieben.

Konfiguration via Settings:
    CRM_DB_NAME, CRM_DB_USER, CRM_DB_PASSWORD, CRM_DB_HOST, CRM_DB_PORT
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from datetime import datetime

import psycopg
from django.utils import timezone

logger = logging.getLogger(__name__)


def _crm_dsn() -> str:
    return psycopg.conninfo.make_conninfo(
        dbname=os.environ.get("CRM_DB_NAME", "piquano_crm_staging"),
        user=os.environ.get("CRM_DB_USER", "crm_user"),
        password=os.environ.get("CRM_DB_PASSWORD", "piquano_crm_2026!"),
        host=os.environ.get("CRM_DB_HOST", "localhost"),
        port=os.environ.get("CRM_DB_PORT", "5432"),
    )


@dataclass
class RemoteMailAccount:
    """Lightweight MailAccount-Proxy, gelesen aus der CRM-DB."""

    pk: str
    user_id: int
    user_username: str
    upn: str
    tenant_id: str
    refresh_token_enc: str
    access_token_cache: str
    access_token_expires_at: datetime | None
    inbox_delta_link: str
    sent_delta_link: str
    last_sync_at: datetime | None
    last_sync_error: str
    status: str

    # Für Kompatibilität mit GraphClient
    @property
    def is_healthy(self):
        return self.status == "connected" and not self.last_sync_error

    class user_proxy:
        """Minimal proxy für account.user.username."""

        def __init__(self, username):
            self.username = username

        def __str__(self):
            return self.username

    @property
    def user(self):
        return self.user_proxy(self.user_username)


_ACCOUNT_FIELDS = """
    ma.id, ma.user_id, u.username, ma.upn, ma.tenant_id,
    ma.refresh_token_enc, ma.access_token_cache, ma.access_token_expires_at,
    ma.inbox_delta_link, ma.sent_delta_link, ma.last_sync_at,
    ma.last_sync_error, ma.status
"""


def get_connected_accounts() -> list[RemoteMailAccount]:
    """Liest alle verbundenen MailAccounts aus der CRM-DB."""
    with psycopg.connect(_crm_dsn()) as conn, conn.cursor() as cur:
        cur.execute(
            f"""
                SELECT {_ACCOUNT_FIELDS}
                FROM ms365_mailaccount ma
                JOIN accounts_user u ON u.id = ma.user_id
                WHERE ma.status = 'connected'
                ORDER BY ma.connected_at DESC
                """
        )
        rows = cur.fetchall()

    return [
        RemoteMailAccount(
            pk=str(row[0]),
            user_id=row[1],
            user_username=row[2],
            upn=row[3],
            tenant_id=row[4],
            refresh_token_enc=row[5],
            access_token_cache=row[6],
            access_token_expires_at=row[7],
            inbox_delta_link=row[8] or "",
            sent_delta_link=row[9] or "",
            last_sync_at=row[10],
            last_sync_error=row[11] or "",
            status=row[12],
        )
        for row in rows
    ]


def get_account_by_upn(upn_substring: str) -> RemoteMailAccount | None:
    """Sucht einen Account per UPN-Substring."""
    accounts = get_connected_accounts()
    for a in accounts:
        if upn_substring.lower() in a.upn.lower():
            return a
    return None


def update_account_field(account_pk: str, **fields) -> None:
    """Schreibt Felder zurück in die CRM-DB (z.B. nach Token-Refresh)."""
    if not fields:
        return
    set_clauses = ", ".join(f"{k} = %s" for k in fields)
    values = list(fields.values()) + [account_pk]
    with psycopg.connect(_crm_dsn()) as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"UPDATE ms365_mailaccount SET {set_clauses} WHERE id = %s",
                values,
            )
        conn.commit()


def update_delta_link(account_pk: str, folder: str, delta_link: str) -> None:
    """Aktualisiert den Delta-Link für einen Ordner."""
    field_name = "inbox_delta_link" if folder == "Inbox" else "sent_delta_link"
    update_account_field(
        account_pk,
        **{field_name: delta_link, "last_sync_at": timezone.now(), "last_sync_error": ""},
    )
