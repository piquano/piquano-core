"""
Migrate existing notes from ATS CandidateNote and CRM Note into SharedNote.

Run from either app:
  python manage.py migrate_notes_to_shared --source ats
  python manage.py migrate_notes_to_shared --source crm
"""
from django.core.management.base import BaseCommand

from piquano_core.shared.models import SharedNote


class Command(BaseCommand):
    help = "Migrate local notes into the shared database"

    def add_arguments(self, parser):
        parser.add_argument(
            "--source", required=True, choices=["ats", "crm"],
            help="Which app's notes to migrate",
        )
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, **options):
        source = options["source"]
        dry_run = options["dry_run"]

        if source == "ats":
            self._migrate_ats(dry_run)
        else:
            self._migrate_crm(dry_run)

    def _migrate_ats(self, dry_run):
        from candidates.models import CandidateNote

        notes = CandidateNote.objects.select_related("candidate").all()
        created, skipped = 0, 0

        for n in notes:
            # Deduplizierung: gleicher Text + gleiche Sekunde = bereits migriert
            exists = SharedNote.objects.filter(
                app_source="ats",
                ats_candidate_id=n.candidate_id,
                created_at__second=n.created_at.second,
                created_at__minute=n.created_at.minute,
                created_at__hour=n.created_at.hour,
                created_at__day=n.created_at.day,
                created_at__month=n.created_at.month,
                created_at__year=n.created_at.year,
                text=n.text,
            ).exists()
            if exists:
                skipped += 1
                continue

            if not dry_run:
                SharedNote.objects.create(
                    app_source="ats",
                    text=n.text,
                    note_type=n.note_type,
                    ats_candidate_id=n.candidate_id,
                    crm_contact_id=n.candidate.crm_contact_id,
                    created_by_name=n.created_by or "System",
                )
            created += 1

        prefix = "[DRY-RUN] " if dry_run else ""
        self.stdout.write(f"{prefix}ATS: {created} migriert, {skipped} übersprungen")

    def _migrate_crm(self, dry_run):
        from contacts.models import Note

        notes = Note.objects.select_related("contact", "created_by").all()
        created, skipped = 0, 0

        for n in notes:
            exists = SharedNote.objects.filter(
                app_source="crm",
                crm_contact_id=n.contact_id,
                created_at__second=n.created_at.second,
                created_at__minute=n.created_at.minute,
                created_at__hour=n.created_at.hour,
                created_at__day=n.created_at.day,
                created_at__month=n.created_at.month,
                created_at__year=n.created_at.year,
                text=n.text,
            ).exists()
            if exists:
                skipped += 1
                continue

            author = ""
            if n.created_by:
                author = n.created_by.get_full_name() or n.created_by.username
            author_email = n.created_by.email if n.created_by else ""

            # Map CRM note_type → shared note_type
            type_map = {
                "note": "general",
                "meeting": "interview",
                "call": "general",
                "comment": "internal",
                "cover_letter": "general",
                "email": "general",
            }

            if not dry_run:
                SharedNote.objects.create(
                    app_source="crm",
                    text=n.text,
                    note_type=type_map.get(n.note_type, "general"),
                    crm_contact_id=n.contact_id,
                    ats_candidate_id=getattr(n.contact, "ats_candidate_id", None),
                    created_by_name=author,
                    created_by_email=author_email,
                )
            created += 1

        prefix = "[DRY-RUN] " if dry_run else ""
        self.stdout.write(f"{prefix}CRM: {created} migriert, {skipped} übersprungen")
