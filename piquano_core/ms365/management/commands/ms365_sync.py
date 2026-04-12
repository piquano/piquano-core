"""
Management-Command: Synchronisiert MS365-Mails für alle verbundenen Accounts.

Usage:
    python manage.py ms365_sync
    python manage.py ms365_sync --account usunkel@piquano.com
    python manage.py ms365_sync --dry-run
    python manage.py ms365_sync --full-resync --backfill-days 30
"""

from django.core.management.base import BaseCommand

from piquano_core.ms365.graph import TokenInvalidError
from piquano_core.ms365.models import MailAccount
from piquano_core.ms365.sync import run_full_sync


class Command(BaseCommand):
    help = 'MS365 Mail-Sync für alle verbundenen Accounts.'

    def add_arguments(self, parser):
        parser.add_argument('--account', help='UPN oder Username (Substring-Match)')
        parser.add_argument('--dry-run', action='store_true')
        parser.add_argument('--full-resync', action='store_true',
                           help='Delta-Links ignorieren, komplett neu syncen')
        parser.add_argument('--backfill-days', type=int, default=30,
                           help='Bei Erstsync/Resync: wie viele Tage zurück (default: 30)')

    def handle(self, *args, **options):
        accounts = MailAccount.objects.filter(status='connected')
        if options['account']:
            q = options['account']
            accounts = accounts.filter(upn__icontains=q) | accounts.filter(user__username__icontains=q)

        if not accounts.exists():
            self.stdout.write(self.style.WARNING('Keine verbundenen Accounts gefunden.'))
            return

        for account in accounts:
            self.stdout.write(f'\nSync: {account.upn}')
            try:
                results = run_full_sync(
                    account,
                    backfill_days=options['backfill_days'],
                    dry_run=options['dry_run'],
                    full_resync=options['full_resync'],
                )
                for folder, r in results.items():
                    self.stdout.write(
                        f'  {folder}: {r.fetched} gelesen, {r.matched} gematcht, '
                        f'{r.persisted_new} neu, {r.persisted_updated} aktualisiert, '
                        f'{r.skipped_no_match} übersprungen, {r.failed} Fehler'
                    )
                    for s in r.sample_subjects:
                        self.stdout.write(f'    → {s}')
            except TokenInvalidError as exc:
                self.stderr.write(self.style.ERROR(f'  Token ungültig: {exc}'))
                self.stderr.write('  → User muss sich unter /ms365/connect/ neu verbinden.')
