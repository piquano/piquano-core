"""
Migrate existing activities from ATS Activity and CRM Activity into SharedActivity.

  python manage.py migrate_activities_to_shared --source ats
  python manage.py migrate_activities_to_shared --source crm
"""
from django.core.management.base import BaseCommand
from piquano_core.shared.models import SharedActivity


class Command(BaseCommand):
    help = "Migrate local activities into the shared database"

    def add_arguments(self, parser):
        parser.add_argument("--source", required=True, choices=["ats", "crm"])
        parser.add_argument("--dry-run", action="store_true")

    def handle(self, **options):
        source = options["source"]
        dry_run = options["dry_run"]
        if source == "ats":
            self._migrate_ats(dry_run)
        else:
            self._migrate_crm(dry_run)

    def _migrate_ats(self, dry_run):
        from candidates.activity import Activity

        created, skipped = 0, 0
        for a in Activity.objects.select_related("candidate").iterator():
            if not dry_run:
                SharedActivity.objects.create(
                    app_source="ats",
                    activity_type=a.activity_type,
                    description=a.description,
                    performed_by_name=a.performed_by or "System",
                    extra=a.extra or {},
                    ats_candidate_id=a.candidate_id,
                    ats_application_id=a.application_id,
                    crm_contact_id=getattr(a.candidate, "crm_contact_id", None) if a.candidate else None,
                )
            created += 1

        prefix = "[DRY-RUN] " if dry_run else ""
        self.stdout.write(f"{prefix}ATS: {created} Aktivitäten migriert")

    def _migrate_crm(self, dry_run):
        from activities.models import Activity

        created, skipped = 0, 0
        for a in Activity.objects.select_related("contact", "activity_type", "assigned_to", "created_by").iterator():
            type_name = a.activity_type.name.lower() if a.activity_type else "task"
            type_map = {
                "anruf": "call", "meeting": "meeting", "aufgabe": "task",
                "e-mail": "email_sent", "notiz": "note_added",
            }
            activity_type = type_map.get(type_name, "task")

            assigned = ""
            if a.assigned_to:
                assigned = a.assigned_to.get_full_name() or a.assigned_to.username
            performed = ""
            if a.created_by:
                performed = a.created_by.get_full_name() or a.created_by.username

            if not dry_run:
                SharedActivity.objects.create(
                    app_source="crm",
                    activity_type=activity_type,
                    subject=a.subject or "",
                    description=a.description or "",
                    due_date=a.due_date,
                    is_done=a.is_done,
                    done_at=a.done_at,
                    performed_by_name=performed,
                    assigned_to_name=assigned,
                    assigned_to_email=a.assigned_to.email if a.assigned_to else "",
                    crm_contact_id=a.contact_id,
                    crm_company_id=a.company_id,
                    crm_deal_id=a.deal_id,
                    ats_candidate_id=getattr(a.contact, "ats_candidate_id", None) if a.contact else None,
                )
            created += 1

        prefix = "[DRY-RUN] " if dry_run else ""
        self.stdout.write(f"{prefix}CRM: {created} Aktivitäten migriert")
