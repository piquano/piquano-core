"""
Signals to mirror local email/activity records into the shared database.

Connect these in the app's AppConfig.ready() method:
    from piquano_core.shared.signals import connect_email_mirror
    connect_email_mirror("ats")  # or "crm"
"""
import logging

from django.db.models.signals import post_save

logger = logging.getLogger(__name__)


def _mirror_ats_email(sender, instance, created, **kwargs):
    """Mirror ATS EmailMessage → SharedEmail on create."""
    if not created:
        return
    try:
        from piquano_core.shared.models import SharedEmail

        # Dedup check
        if instance.graph_message_id and SharedEmail.objects.filter(
            graph_message_id=instance.graph_message_id
        ).exists():
            return

        SharedEmail.objects.create(
            app_source="ats",
            from_email=instance.from_email or "",
            from_name=instance.from_name or "",
            to_email=instance.to_email or "",
            to_name=instance.to_name or "",
            to_emails=instance.to_emails or "",
            cc_emails=instance.cc_emails or "",
            subject=instance.subject or "",
            body_text=instance.body_text or "",
            body_html=instance.body_html or "",
            direction=instance.direction or "outbound",
            status=instance.status or "sent",
            graph_message_id=instance.graph_message_id or "",
            internet_message_id=instance.internet_message_id or "",
            conversation_id=instance.conversation_id or "",
            mailjet_message_id=str(instance.mailjet_message_id) if instance.mailjet_message_id else "",
            thread_subject=instance.thread_subject or "",
            sent_at=instance.sent_at,
            opened_at=instance.opened_at,
            sent_by_name=instance.sent_by or "",
            ats_candidate_id=instance.candidate_id,
            ats_application_id=instance.application_id,
            crm_contact_id=getattr(instance.candidate, "crm_contact_id", None) if instance.candidate else None,
        )
    except Exception:
        logger.exception("Failed to mirror ATS email to shared DB")


def _mirror_crm_email(sender, instance, created, **kwargs):
    """Mirror CRM EmailLog → SharedEmail on create."""
    if not created:
        return
    try:
        from piquano_core.shared.models import SharedEmail

        if instance.graph_message_id and SharedEmail.objects.filter(
            graph_message_id=instance.graph_message_id
        ).exists():
            return

        direction_map = {"out": "outbound", "in": "inbound"}
        status_map = {
            "sent": "sent", "failed": "failed", "opened": "opened",
            "clicked": "opened", "bounced": "bounced", "received": "received",
        }
        sent_by = ""
        sent_by_email = ""
        if instance.sent_by:
            sent_by = instance.sent_by.get_full_name() or instance.sent_by.username
            sent_by_email = instance.sent_by.email or ""

        SharedEmail.objects.create(
            app_source="crm",
            from_email=instance.from_email or "",
            to_email=getattr(instance, "recipient_email", "") or "",
            to_emails=instance.to_emails or "",
            cc_emails=instance.cc_emails or "",
            subject=instance.subject or "",
            body_html=instance.body_html or "",
            direction=direction_map.get(instance.direction, "outbound"),
            status=status_map.get(instance.status, "sent"),
            graph_message_id=instance.graph_message_id or "",
            internet_message_id=instance.internet_message_id or "",
            conversation_id=instance.conversation_id or "",
            mailjet_message_id=instance.mailjet_message_id or "",
            sent_at=instance.sent_at,
            opened_at=instance.opened_at,
            received_at=getattr(instance, "received_at", None),
            has_attachments=getattr(instance, "has_attachments", False),
            sent_by_name=sent_by,
            sent_by_email=sent_by_email,
            crm_contact_id=instance.contact_id,
            ats_candidate_id=getattr(instance.contact, "ats_candidate_id", None) if instance.contact else None,
        )
    except Exception:
        logger.exception("Failed to mirror CRM email to shared DB")


def _mirror_ats_activity(sender, instance, created, **kwargs):
    """Mirror ATS Activity → SharedActivity on create."""
    if not created:
        return
    try:
        from piquano_core.shared.models import SharedActivity
        SharedActivity.objects.create(
            app_source="ats",
            activity_type=instance.activity_type,
            description=instance.description,
            performed_by_name=instance.performed_by or "System",
            extra=instance.extra or {},
            ats_candidate_id=instance.candidate_id,
            ats_application_id=instance.application_id,
            crm_contact_id=getattr(instance.candidate, "crm_contact_id", None) if instance.candidate else None,
        )
    except Exception:
        logger.exception("Failed to mirror ATS activity to shared DB")


def _mirror_crm_activity(sender, instance, created, **kwargs):
    """Mirror CRM Activity → SharedActivity on create."""
    if not created:
        return
    try:
        from piquano_core.shared.models import SharedActivity
        type_name = instance.activity_type.name.lower() if instance.activity_type else "task"
        type_map = {
            "anruf": "call", "meeting": "meeting", "aufgabe": "task",
            "e-mail": "email_sent", "notiz": "note_added",
        }
        performed = ""
        if instance.created_by:
            performed = instance.created_by.get_full_name() or instance.created_by.username
        assigned = ""
        if instance.assigned_to:
            assigned = instance.assigned_to.get_full_name() or instance.assigned_to.username

        SharedActivity.objects.create(
            app_source="crm",
            activity_type=type_map.get(type_name, "task"),
            subject=instance.subject or "",
            description=instance.description or "",
            due_date=instance.due_date,
            is_done=instance.is_done,
            done_at=instance.done_at,
            performed_by_name=performed,
            assigned_to_name=assigned,
            crm_contact_id=instance.contact_id,
            crm_company_id=instance.company_id,
            crm_deal_id=instance.deal_id,
            ats_candidate_id=getattr(instance.contact, "ats_candidate_id", None) if instance.contact else None,
        )
    except Exception:
        logger.exception("Failed to mirror CRM activity to shared DB")


def connect_email_mirror(app_source):
    """Call from AppConfig.ready() to connect the email signal."""
    if app_source == "ats":
        from mail.models import EmailMessage
        post_save.connect(_mirror_ats_email, sender=EmailMessage, dispatch_uid="shared_mirror_ats_email")
    elif app_source == "crm":
        from emails.models import EmailLog
        post_save.connect(_mirror_crm_email, sender=EmailLog, dispatch_uid="shared_mirror_crm_email")


def connect_activity_mirror(app_source):
    """Call from AppConfig.ready() to connect the activity signal."""
    if app_source == "ats":
        from candidates.activity import Activity
        post_save.connect(_mirror_ats_activity, sender=Activity, dispatch_uid="shared_mirror_ats_activity")
    elif app_source == "crm":
        from activities.models import Activity
        post_save.connect(_mirror_crm_activity, sender=Activity, dispatch_uid="shared_mirror_crm_activity")
