"""Shared utilities for MS365 mail processing."""

from __future__ import annotations


def addresses_from_message(msg: dict) -> set[str]:
    """Extrahiert alle Mail-Adressen aus einem Graph-Message-JSON."""
    addrs: set[str] = set()

    def _add(entry):
        if not entry:
            return
        ea = entry.get('emailAddress') or {}
        addr = (ea.get('address') or '').strip().lower()
        if addr:
            addrs.add(addr)

    for key in ('from', 'sender'):
        _add(msg.get(key))
    for key in ('toRecipients', 'ccRecipients', 'bccRecipients', 'replyTo'):
        for entry in msg.get(key) or []:
            _add(entry)
    return addrs


def parse_received(msg: dict, folder: str):
    """Parse receivedDateTime/sentDateTime from a Graph message."""
    from datetime import timezone as dt_timezone
    from django.utils.dateparse import parse_datetime

    raw = msg.get('receivedDateTime') if folder == 'Inbox' else msg.get('sentDateTime')
    if not raw:
        return None
    dt = parse_datetime(raw)
    if dt and dt.tzinfo is None:
        dt = dt.replace(tzinfo=dt_timezone.utc)
    return dt


def direction_for_folder(folder: str) -> str:
    return 'in' if folder == 'Inbox' else 'out'
