"""
Helper to build unified timeline entries from SharedNote, SharedEmail, SharedActivity.

Usage in a view:
    from piquano_core.shared.timeline import build_timeline
    timeline_entries = build_timeline(ats_candidate_id=..., crm_contact_id=...)
"""
from datetime import date, timedelta

from django.utils import timezone

from .models import SharedNote, SharedEmail, SharedActivity


def _strip_html(html):
    """Strip HTML tags and collapse whitespace for plaintext display."""
    if not html:
        return ""
    import re
    text = re.sub(r"<br\s*/?>", "\n", html, flags=re.IGNORECASE)
    text = re.sub(r"</(p|div|tr|li)>", "\n", text, flags=re.IGNORECASE)
    text = re.sub(r"<[^>]+>", "", text)
    text = re.sub(r"&nbsp;", " ", text)
    text = re.sub(r"&amp;", "&", text)
    text = re.sub(r"&lt;", "<", text)
    text = re.sub(r"&gt;", ">", text)
    text = re.sub(r"&quot;", '"', text)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


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


def build_timeline(ats_candidate_id=None, crm_contact_id=None, limit=50, notes_cutoff=None, hide_piquano_sender=False):
    """Build a unified timeline from shared models.

    Returns a list of dicts ready for the unified_timeline.html template.

    Args:
        notes_cutoff: Optional datetime — if set, only notes created after
            this date are included. E-Mails and activities are not affected.
        hide_piquano_sender: If True, exclude all emails sent from @piquano.com
            (used for partner timelines where internal mails are irrelevant).
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
    notes_q = q
    if notes_cutoff:
        notes_q = notes_q & Q(created_at__gte=notes_cutoff)
    for n in SharedNote.objects.filter(notes_q).order_by("-created_at")[:limit]:
        entries.append({
            "type": "note",
            "date": n.created_at,
            "date_group": _date_group(n.created_at),
            "text": n.text,
            "author": n.created_by_name or "System",
            "author_email": n.created_by_email or "",
            "source": n.app_source,
            "note_id": str(n.pk),
            "extra": {"note_type": n.note_type, "note_type_label": _note_type_label(n.note_type)},
        })

    # Emails: bei Partnern alle von Piquano gesendeten E-Mails ausblenden
    # (@piquano.com-Absender + System-Mails ohne Absender),
    # sonst nur interne @piquano.com → @piquano.com
    email_qs = SharedEmail.objects.filter(q)
    if hide_piquano_sender:
        email_qs = email_qs.exclude(
            from_email__iendswith="@piquano.com",
        ).exclude(
            from_email="", direction="outbound",
        )
    else:
        email_qs = email_qs.exclude(
            from_email__iendswith="@piquano.com",
            to_email__iendswith="@piquano.com",
        )

    # Dedup: Mailjet erzeugt pro Empfänger unterschiedliche Message-IDs,
    # daher landen Multi-Postfach-Kopien + das Versand-Original als separate
    # SharedEmail-Einträge. Zusammenfassen über subject+from+to im 5-Min-Fenster.
    seen_email_keys = {}
    for e in email_qs.order_by("-created_at")[:limit]:
        dt = e.sent_at or e.received_at or e.created_at
        # Dedup-Schlüssel: subject + from + to, gerundet auf 5-Minuten-Fenster
        bucket = int(dt.timestamp()) // 300
        dedup_key = (e.subject, e.from_email, e.to_email, bucket)
        if dedup_key in seen_email_keys:
            # outbound (Versand-Original) bevorzugen gegenüber inbound (Sync-Kopie)
            if e.direction == "outbound":
                seen_email_keys[dedup_key]["direction"] = "outbound"
                seen_email_keys[dedup_key]["source"] = e.app_source
            continue
        entry = {
            "type": "email",
            "date": dt,
            "date_group": _date_group(dt),
            "text": _strip_html(e.body_html) or e.body_text or "",
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
        }
        seen_email_keys[dedup_key] = entry
        entries.append(entry)

    # Activities — note_added und email_sent ausschließen, weil Notizen und
    # E-Mails bereits als eigene Einträge in der Timeline erscheinen.
    activity_qs = SharedActivity.objects.filter(q).exclude(
        activity_type__in=("note_added", "email_sent"),
    )
    for a in activity_qs.order_by("-created_at")[:limit]:
        # Alert-Subscriptions als eigenen Typ "alert" durchreichen
        entry_type = "alert" if a.activity_type == "alert_subscribed" else "activity"
        entries.append({
            "type": entry_type,
            "date": a.created_at,
            "date_group": _date_group(a.created_at),
            "text": a.description,
            "subject": a.subject,
            "author": a.performed_by_name or "System",
            "source": a.app_source,
            "activity_id": str(a.pk),
            "extra": {
                "activity_type": a.activity_type,
                "due_date": a.due_date.strftime("%d.%m.%Y %H:%M") if a.due_date else "",
                "is_done": a.is_done,
            },
        })

    # Sort all entries by date descending
    entries.sort(key=lambda e: e["date"], reverse=True)

    return entries[:limit]
