"""
Management-Command: Backfill der letzten N Tage E-Mails.

Usage:
    python manage.py ms365_backfill --days 30
    python manage.py ms365_backfill --days 7 --account usunkel@piquano.com
    python manage.py ms365_backfill --days 30 --dry-run
"""

from __future__ import annotations

from django.core.management.base import BaseCommand

from piquano_core.ms365.graph import TokenInvalidError
from piquano_core.ms365.management.commands.ms365_sync import _get_accounts
from piquano_core.ms365.sync import run_full_sync


class Command(BaseCommand):
    help = "Backfill: importiert die letzten N Tage E-Mails für alle verbundenen Accounts."

    def add_arguments(self, parser):
        parser.add_argument("--days", type=int, default=30, help="Tage zurück (default: 30)")
        parser.add_argument("--account", help="UPN oder Username (Substring-Match)")
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, *args, **options):
        days = options["days"]
        accounts = _get_accounts(options["account"])
        if not accounts:
            self.stdout.write(self.style.WARNING("Keine verbundenen Accounts gefunden."))
            return

        prefix = "[DRY-RUN] " if options["dry_run"] else ""

        for account in accounts:
            self.stdout.write(f"\n{prefix}Backfill {days} Tage: {account.upn}")
            try:
                results = run_full_sync(
                    account,
                    backfill_days=days,
                    dry_run=options["dry_run"],
                    full_resync=True,
                )
                total_new = sum(r.persisted_new for r in results.values())
                total_fetched = sum(r.fetched for r in results.values())
                total_matched = sum(r.matched for r in results.values())

                self.stdout.write(
                    f"  {prefix}Gelesen: {total_fetched}, Gematcht: {total_matched}, Neu: {total_new}"
                )
                for folder, r in results.items():
                    self.stdout.write(
                        f"  {folder}: {r.fetched} gelesen, {r.persisted_new} neu, "
                        f"{r.skipped_no_match} übersprungen"
                    )
            except TokenInvalidError as exc:
                self.stderr.write(self.style.ERROR(f"  Token ungültig: {exc}"))
