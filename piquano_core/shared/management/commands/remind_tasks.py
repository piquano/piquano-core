"""
Sendet E-Mail-Reminder fuer faellige Aufgaben (SharedActivity).

- 1 Tag vorher: "Erinnerung: Morgen faellig"
- Am Tag: "Heute faellig"
- Nur fuer is_done=False mit due_date

Usage:
    python manage.py remind_tasks              # Sendet Reminder
    python manage.py remind_tasks --dry-run    # Nur anzeigen
"""

import logging
import os
from datetime import timedelta

import requests
from django.core.management.base import BaseCommand
from django.utils import timezone

logger = logging.getLogger(__name__)


def _send_mailjet(to_email, to_name, subject, body_html):
    """Einfacher Mailjet v3.1 Send."""
    api_key = os.getenv("MAILJET_API_KEY", "")
    secret_key = os.getenv("MAILJET_SECRET_KEY", "")
    if not api_key or not secret_key:
        logger.error("MAILJET_API_KEY/SECRET_KEY nicht gesetzt")
        return False

    resp = requests.post(
        "https://api.mailjet.com/v3.1/send",
        auth=(api_key, secret_key),
        json={
            "Messages": [
                {
                    "From": {"Email": "noreply@piquano.com", "Name": "Piquano"},
                    "To": [{"Email": to_email, "Name": to_name}],
                    "Subject": subject,
                    "HTMLPart": body_html,
                }
            ]
        },
        timeout=10,
    )
    if resp.status_code == 200:
        logger.info("Reminder-Mail gesendet an %s: %s", to_email, subject)
        return True
    logger.error("Mailjet-Fehler %s: %s", resp.status_code, resp.text[:200])
    return False


def _build_reminder_html(tasks_overdue, tasks_today, tasks_tomorrow):
    """Eine einzelne Mail mit allen Aufgaben gruppiert."""

    def _task_row(t, color):
        date_str = t.due_date.strftime("%d.%m.%Y %H:%M") if t.due_date else "—"
        return (
            f"<tr>"
            f"<td style='padding:6px 12px;border-bottom:1px solid #f1f5f9;border-left:3px solid {color};'>"
            f"{t.subject or '(ohne Titel)'}</td>"
            f"<td style='padding:6px 12px;border-bottom:1px solid #f1f5f9;color:#64748b;white-space:nowrap;'>{date_str}</td>"
            f"<td style='padding:6px 12px;border-bottom:1px solid #f1f5f9;color:#64748b;'>"
            f"{t.assigned_to_name or t.performed_by_name or '—'}</td>"
            f"</tr>"
        )

    def _group_header(label, color):
        return (
            f"<tr><td colspan='3' style='padding:10px 12px 4px;font-size:11px;font-weight:700;"
            f"text-transform:uppercase;letter-spacing:0.04em;color:{color};'>{label}</td></tr>"
        )

    rows = ""
    if tasks_overdue:
        rows += _group_header(f"Ueberfaellig ({len(tasks_overdue)})", "#dc2626")
        for t in tasks_overdue:
            rows += _task_row(t, "#dc2626")
    if tasks_today:
        rows += _group_header(f"Heute faellig ({len(tasks_today)})", "#d97706")
        for t in tasks_today:
            rows += _task_row(t, "#d97706")
    if tasks_tomorrow:
        rows += _group_header(f"Morgen faellig ({len(tasks_tomorrow)})", "#328cc1")
        for t in tasks_tomorrow:
            rows += _task_row(t, "#328cc1")

    total = len(tasks_overdue) + len(tasks_today) + len(tasks_tomorrow)

    return f"""
    <div style="font-family:Inter,-apple-system,sans-serif;max-width:600px;margin:0 auto;">
        <div style="background:#133447;padding:16px 24px;border-radius:8px 8px 0 0;">
            <img src="https://app.piquano.com/static/img/piquano-logo-white.png" alt="Piquano" height="24" style="display:block;">
        </div>
        <div style="background:#fff;padding:24px;border:1px solid #e5e7eb;border-top:none;">
            <h2 style="color:#133447;margin:0 0 8px;font-size:18px;">{total} Aufgabe{"n" if total != 1 else ""}</h2>
            <p style="color:#666;font-size:14px;line-height:1.5;margin:0 0 16px;">Folgende Aufgaben erfordern deine Aufmerksamkeit:</p>
            <table style="width:100%;border-collapse:collapse;font-size:13px;">
                {rows}
            </table>
            <div style="margin-top:20px;">
                <a href="https://crm.piquano.com/dashboard/" style="background:#328cc1;color:#fff;padding:10px 20px;border-radius:6px;text-decoration:none;font-weight:600;font-size:13px;display:inline-block;">Im Dashboard ansehen</a>
            </div>
        </div>
        <div style="padding:12px 24px;font-size:11px;color:#9ca3af;text-align:center;border:1px solid #e5e7eb;border-top:none;border-radius:0 0 8px 8px;">
            <a href="https://piquano.com/datenschutz" style="color:#9ca3af;">Datenschutz</a> &middot;
            <a href="https://piquano.com/impressum" style="color:#9ca3af;">Impressum</a>
        </div>
    </div>
    """


class Command(BaseCommand):
    help = "Sendet E-Mail-Reminder fuer faellige Aufgaben (morgen + heute)"

    def add_arguments(self, parser):
        parser.add_argument("--dry-run", action="store_true", help="Nur anzeigen")
        parser.add_argument(
            "--admin", default="usunkel@piquano.com",
            help="Admin bekommt ALLE Aufgaben (zusaetzlich zu individuellen Mails)",
        )

    def _get_email(self, task):
        """Empfaenger: assigned_to_email > performed_by_email."""
        return task.assigned_to_email or task.performed_by_email or ""

    def handle(self, *args, **options):
        from collections import defaultdict
        from piquano_core.shared.models import SharedActivity

        now = timezone.localtime()
        today_start = now.replace(hour=0, minute=0, second=0, microsecond=0)
        today_end = today_start + timedelta(days=1)
        tomorrow_end = today_start + timedelta(days=2)

        dry_run = options["dry_run"]
        admin_email = options["admin"]

        all_tasks = list(
            SharedActivity.objects.filter(
                is_done=False, due_date__isnull=False, due_date__lt=tomorrow_end
            ).order_by("due_date")
        )

        if not all_tasks:
            self.stdout.write("Keine faelligen Aufgaben — kein Reminder noetig.")
            return

        # Pro Empfaenger gruppieren
        by_recipient = defaultdict(list)
        for t in all_tasks:
            email = self._get_email(t)
            if email:
                by_recipient[email].append(t)
            # Admin bekommt immer alles
            if email != admin_email:
                by_recipient[admin_email].append(t)

        self.stdout.write(f"{len(all_tasks)} Aufgaben, {len(by_recipient)} Empfaenger")

        for recipient, tasks in by_recipient.items():
            overdue = [t for t in tasks if t.due_date < today_start]
            today = [t for t in tasks if today_start <= t.due_date < today_end]
            tomorrow = [t for t in tasks if today_end <= t.due_date < tomorrow_end]

            total = len(overdue) + len(today) + len(tomorrow)
            if total == 0:
                continue

            self.stdout.write(f"  {recipient}: {len(overdue)} ueberfaellig, {len(today)} heute, {len(tomorrow)} morgen")

            if dry_run:
                for t in overdue + today + tomorrow:
                    self.stdout.write(f"    {t.due_date:%d.%m. %H:%M} | {t.subject} | {t.assigned_to_name or t.performed_by_name}")
                continue

            html = _build_reminder_html(overdue, today, tomorrow)

            parts = []
            if overdue:
                parts.append(f"{len(overdue)} ueberfaellig")
            if today:
                parts.append(f"{len(today)} heute")
            if tomorrow:
                parts.append(f"{len(tomorrow)} morgen")
            subject = f"[Piquano] Aufgaben: {', '.join(parts)}"

            ok = _send_mailjet(recipient, "", subject, html)
            if ok:
                self.stdout.write(self.style.SUCCESS(f"  Reminder gesendet an {recipient}"))
                from piquano_core.shared.models import EmailLog

                EmailLog.log(
                    app="core",
                    email_type="Aufgaben-Reminder",
                    recipient=recipient,
                    subject=subject,
                    status="sent",
                )
            else:
                self.stdout.write(self.style.ERROR(f"  Mail fehlgeschlagen: {recipient}"))

        if dry_run:
            self.stdout.write("\nDRY-RUN — keine Mails gesendet.")
