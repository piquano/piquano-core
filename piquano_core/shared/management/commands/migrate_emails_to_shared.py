"""
Migrate existing emails from ATS EmailMessage and CRM EmailLog into SharedEmail.

  python manage.py migrate_emails_to_shared --source ats
  python manage.py migrate_emails_to_shared --source crm
"""
from django.core.management.base import BaseCommand
from piquano_core.shared.models import SharedEmail


class Command(BaseCommand):
    help = "Migrate local emails into the shared database"

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
        from mail.models import EmailMessage

        created, skipped = 0, 0
        for m in EmailMessage.objects.select_related("candidate").iterator():
            # Dedup by graph_message_id or internet_message_id or (from+to+subject+sent_at)
            if m.graph_message_id and SharedEmail.objects.filter(graph_message_id=m.graph_message_id).exists():
                skipped += 1
                continue
            if m.internet_message_id and SharedEmail.objects.filter(internet_message_id=m.internet_message_id).exists():
                skipped += 1
                continue

            direction_map = {"outbound": "outbound", "inbound": "inbound"}
            status_map = {
                "draft": "draft", "sent": "sent", "delivered": "delivered",
                "opened": "opened", "bounced": "bounced", "failed": "failed",
            }

            if not dry_run:
                SharedEmail.objects.create(
                    app_source="ats",
                    from_email=m.from_email or "",
                    from_name=m.from_name or "",
                    to_email=m.to_email or "",
                    to_name=m.to_name or "",
                    to_emails=m.to_emails or "",
                    cc_emails=m.cc_emails or "",
                    subject=m.subject or "",
                    body_text=m.body_text or "",
                    body_html=m.body_html or "",
                    direction=direction_map.get(m.direction, "outbound"),
                    status=status_map.get(m.status, "sent"),
                    graph_message_id=m.graph_message_id or "",
                    internet_message_id=m.internet_message_id or "",
                    conversation_id=m.conversation_id or "",
                    mailjet_message_id=str(m.mailjet_message_id) if m.mailjet_message_id else "",
                    thread_subject=m.thread_subject or "",
                    sent_at=m.sent_at,
                    opened_at=m.opened_at,
                    has_attachments=False,
                    sent_by_name=m.sent_by or "",
                    ats_candidate_id=m.candidate_id,
                    ats_application_id=m.application_id,
                    crm_contact_id=getattr(m.candidate, "crm_contact_id", None) if m.candidate else None,
                )
            created += 1

        prefix = "[DRY-RUN] " if dry_run else ""
        self.stdout.write(f"{prefix}ATS: {created} E-Mails migriert, {skipped} Duplikate übersprungen")

    def _migrate_crm(self, dry_run):
        from emails.models import EmailLog

        created, skipped = 0, 0
        for m in EmailLog.objects.select_related("contact", "sent_by").iterator():
            if m.graph_message_id and SharedEmail.objects.filter(graph_message_id=m.graph_message_id).exists():
                skipped += 1
                continue
            if m.internet_message_id and SharedEmail.objects.filter(internet_message_id=m.internet_message_id).exists():
                skipped += 1
                continue

            direction_map = {"out": "outbound", "in": "inbound"}
            status_map = {
                "sent": "sent", "failed": "failed", "opened": "opened",
                "clicked": "opened", "bounced": "bounced", "received": "received",
            }

            sent_by = ""
            if m.sent_by:
                sent_by = m.sent_by.get_full_name() or m.sent_by.username

            if not dry_run:
                SharedEmail.objects.create(
                    app_source="crm",
                    from_email=m.from_email or "",
                    to_email=m.recipient_email or "",
                    to_emails=m.to_emails or "",
                    cc_emails=m.cc_emails or "",
                    subject=m.subject or "",
                    body_text="",
                    body_html=m.body_html or "",
                    direction=direction_map.get(m.direction, "outbound"),
                    status=status_map.get(m.status, "sent"),
                    graph_message_id=m.graph_message_id or "",
                    internet_message_id=m.internet_message_id or "",
                    conversation_id=m.conversation_id or "",
                    mailjet_message_id=m.mailjet_message_id or "",
                    sent_at=m.sent_at,
                    opened_at=m.opened_at,
                    received_at=m.received_at,
                    has_attachments=m.has_attachments,
                    sent_by_name=sent_by,
                    sent_by_email=m.sent_by.email if m.sent_by else "",
                    crm_contact_id=m.contact_id,
                    ats_candidate_id=getattr(m.contact, "ats_candidate_id", None) if m.contact else None,
                )
            created += 1

        prefix = "[DRY-RUN] " if dry_run else ""
        self.stdout.write(f"{prefix}CRM: {created} E-Mails migriert, {skipped} Duplikate übersprungen")
