"""
Helper to build unified timeline entries from SharedNote, SharedEmail, SharedActivity.

Usage in a view:
    from piquano_core.shared.timeline import build_timeline
    timeline_entries = build_timeline(ats_candidate_id=..., crm_contact_id=...)
"""
from datetime import date, timedelta

from django.utils import timezone

from .models import SharedNote, SharedEmail, SharedActivity


def _date_group(dt):
    """Return a human-readable date group label."""
    today = timezone.localdate()
    d = dt.date() if hasattr(dt, "date") else dt
    if d == today:
        return "Heute"
    if d == today - timedelta(days=1):
        return "Gestern"
    return d.strftime("%d.%m.%Y")


def _note_type_label(note_type):
    return {
        "general": "Notiz",
        "interview": "Interview",
        "internal": "Intern",
        "feedback": "Feedback",
    }.get(note_type, "Notiz")


def build_timeline(ats_candidate_id=None, crm_contact_id=None, limit=50):
    """Build a unified timeline from shared models.

    Returns a list of dicts ready for the unified_timeline.html template.
    """
    from django.db.models import Q

    q = Q()
    if ats_candidate_id:
        q |= Q(ats_candidate_id=ats_candidate_id)
    if crm_contact_id:
        q |= Q(crm_contact_id=crm_contact_id)
    if not q:
        return []

    entries = []

    # Notes
    for n in SharedNote.objects.filter(q).order_by("-created_at")[:limit]:
        entries.append({
            "type": "note",
            "date": n.created_at,
            "date_group": _date_group(n.created_at),
            "text": n.text,
            "author": n.created_by_name or "System",
            "source": n.app_source,
            "extra": {"note_type": n.note_type, "note_type_label": _note_type_label(n.note_type)},
        })

    # Emails
    for e in SharedEmail.objects.filter(q).order_by("-created_at")[:limit]:
        dt = e.sent_at or e.received_at or e.created_at
        entries.append({
            "type": "email",
            "date": dt,
            "date_group": _date_group(dt),
            "text": e.body_text or e.body_html or "",
            "subject": e.subject,
            "author": e.sent_by_name or e.from_name or e.from_email,
            "source": e.app_source,
            "direction": e.direction,
            "status": e.status,
            "extra": {
                "from_email": e.from_email,
                "to_email": e.to_email,
                "body_html": e.body_html,
            },
        })

    # Activities
    for a in SharedActivity.objects.filter(q).order_by("-created_at")[:limit]:
        entries.append({
            "type": "activity",
            "date": a.created_at,
            "date_group": _date_group(a.created_at),
            "text": a.description,
            "subject": a.subject,
            "author": a.performed_by_name or "System",
            "source": a.app_source,
            "extra": {"activity_type": a.activity_type},
        })

    # Sort all entries by date descending
    entries.sort(key=lambda e: e["date"], reverse=True)

    return entries[:limit]
