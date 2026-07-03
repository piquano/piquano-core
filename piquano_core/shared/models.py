import uuid

from django.db import models


class AppSource(models.TextChoices):
    ATS = "ats", "ATS"
    CRM = "crm", "CRM"


# ---------------------------------------------------------------------------
# Shared Note
# ---------------------------------------------------------------------------

class NoteType(models.TextChoices):
    GENERAL = "general", "Allgemein"
    INTERVIEW = "interview", "Interview"
    INTERNAL = "internal", "Intern"
    FEEDBACK = "feedback", "Feedback"


class SharedNote(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    app_source = models.CharField(
        "Quelle", max_length=10, choices=AppSource.choices,
        help_text="App, in der die Notiz erstellt wurde",
    )
    text = models.TextField("Notiz")
    note_type = models.CharField(
        max_length=20, choices=NoteType.choices, default=NoteType.GENERAL,
    )

    # Personenbezug (UUID ohne FK — funktioniert cross-DB)
    ats_candidate_id = models.UUIDField(null=True, blank=True, db_index=True)
    crm_contact_id = models.UUIDField(null=True, blank=True, db_index=True)

    # Autor
    created_by_name = models.CharField("Autor", max_length=200, blank=True)
    created_by_email = models.EmailField("Autor E-Mail", blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "shared_note"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["ats_candidate_id", "-created_at"]),
            models.Index(fields=["crm_contact_id", "-created_at"]),
        ]
        verbose_name = "Notiz"
        verbose_name_plural = "Notizen"

    def __str__(self):
        return f"{self.get_app_source_display()}: {self.text[:60]}"


# ---------------------------------------------------------------------------
# Shared Email
# ---------------------------------------------------------------------------

class EmailDirection(models.TextChoices):
    OUTBOUND = "outbound", "Ausgehend"
    INBOUND = "inbound", "Eingehend"


class EmailStatus(models.TextChoices):
    DRAFT = "draft", "Entwurf"
    SENT = "sent", "Gesendet"
    DELIVERED = "delivered", "Zugestellt"
    OPENED = "opened", "Geöffnet"
    BOUNCED = "bounced", "Bounce"
    FAILED = "failed", "Fehlgeschlagen"
    RECEIVED = "received", "Empfangen"


class SharedEmail(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    app_source = models.CharField(max_length=10, choices=AppSource.choices)

    # Absender / Empfänger
    from_email = models.EmailField("Von")
    from_name = models.CharField(max_length=200, blank=True)
    to_email = models.EmailField("An")
    to_name = models.CharField(max_length=200, blank=True)
    to_emails = models.TextField("Weitere Empfänger (CSV)", blank=True)
    cc_emails = models.TextField("CC (CSV)", blank=True)

    # Inhalt
    subject = models.CharField("Betreff", max_length=500)
    body_text = models.TextField("Text", blank=True)
    body_html = models.TextField("HTML", blank=True)

    # Status
    direction = models.CharField(
        max_length=10, choices=EmailDirection.choices, default=EmailDirection.OUTBOUND,
    )
    status = models.CharField(
        max_length=10, choices=EmailStatus.choices, default=EmailStatus.DRAFT,
    )

    # Provider-Referenzen (Deduplizierung)
    graph_message_id = models.CharField(max_length=255, blank=True, db_index=True)
    internet_message_id = models.CharField(max_length=998, blank=True, db_index=True)
    conversation_id = models.CharField(max_length=255, blank=True, db_index=True)
    mailjet_message_id = models.CharField(max_length=100, blank=True, db_index=True)

    # Threading
    in_reply_to_id = models.UUIDField(
        "Antwort auf", null=True, blank=True,
        help_text="UUID einer anderen SharedEmail",
    )
    thread_subject = models.CharField(max_length=500, blank=True)

    # Zeitstempel
    sent_at = models.DateTimeField(null=True, blank=True)
    opened_at = models.DateTimeField(null=True, blank=True)
    received_at = models.DateTimeField(null=True, blank=True)
    has_attachments = models.BooleanField(default=False)
    error_message = models.TextField(blank=True)

    # Autor
    sent_by_name = models.CharField(max_length=200, blank=True)
    sent_by_email = models.EmailField(blank=True)

    # Personenbezug (UUID ohne FK)
    ats_candidate_id = models.UUIDField(null=True, blank=True, db_index=True)
    ats_application_id = models.UUIDField(null=True, blank=True, db_index=True)
    crm_contact_id = models.UUIDField(null=True, blank=True, db_index=True)
    crm_deal_id = models.UUIDField(null=True, blank=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "shared_email"
        ordering = ["-sent_at", "-created_at"]
        indexes = [
            models.Index(fields=["ats_candidate_id", "-created_at"]),
            models.Index(fields=["crm_contact_id", "-created_at"]),
            models.Index(fields=["conversation_id", "-created_at"]),
        ]
        verbose_name = "E-Mail"
        verbose_name_plural = "E-Mails"

    def __str__(self):
        return f"{self.direction}: {self.subject[:60]}"


# ---------------------------------------------------------------------------
# Shared Activity
# ---------------------------------------------------------------------------

class ActivityType(models.TextChoices):
    # Allgemein
    NOTE_ADDED = "note_added", "Notiz hinzugefügt"
    CALL = "call", "Anruf"
    MEETING = "meeting", "Meeting"
    EMAIL_SENT = "email_sent", "E-Mail gesendet"
    EMAIL_RECEIVED = "email_received", "E-Mail empfangen"
    TASK = "task", "Aufgabe"
    # ATS-spezifisch
    CANDIDATE_CREATED = "candidate_created", "Kandidat angelegt"
    CANDIDATE_UPDATED = "candidate_updated", "Kandidat aktualisiert"
    APPLICATION_CREATED = "application_created", "Bewerbung eingegangen"
    STAGE_MOVED = "stage_moved", "Stage verschoben"
    STATUS_CHANGED = "status_changed", "Status geändert"
    AI_SCORED = "ai_scored", "KI-Scoring"
    # Karriereseite / Alerts
    ALERT_SUBSCRIBED = "alert_subscribed", "Projekt-Alert abonniert"
    # CRM-spezifisch
    DEAL_CREATED = "deal_created", "Deal angelegt"
    DEAL_WON = "deal_won", "Deal gewonnen"
    DEAL_LOST = "deal_lost", "Deal verloren"


class SharedActivity(models.Model):
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    app_source = models.CharField(max_length=10, choices=AppSource.choices)
    activity_type = models.CharField(max_length=30, choices=ActivityType.choices)

    subject = models.CharField("Betreff", max_length=200, blank=True)
    description = models.TextField("Beschreibung", blank=True)

    # Aufgaben-Felder (CRM-Stil)
    due_date = models.DateTimeField("Fällig am", null=True, blank=True)
    is_done = models.BooleanField("Erledigt", default=False)
    done_at = models.DateTimeField(null=True, blank=True)

    # Autor / Zuständig
    performed_by_name = models.CharField(max_length=200, blank=True)
    performed_by_email = models.EmailField(blank=True)
    assigned_to_name = models.CharField(max_length=200, blank=True)
    assigned_to_email = models.EmailField(blank=True)

    # Flexible Zusatzdaten
    extra = models.JSONField(default=dict, blank=True)

    # Personenbezug (UUID ohne FK)
    related_name = models.CharField("Personen-Name", max_length=200, blank=True)
    ats_candidate_id = models.UUIDField(null=True, blank=True, db_index=True)
    ats_application_id = models.UUIDField(null=True, blank=True, db_index=True)
    crm_contact_id = models.UUIDField(null=True, blank=True, db_index=True)
    crm_company_id = models.UUIDField(null=True, blank=True, db_index=True)
    crm_deal_id = models.UUIDField(null=True, blank=True, db_index=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "shared_activity"
        ordering = ["-created_at"]
        indexes = [
            models.Index(fields=["ats_candidate_id", "-created_at"]),
            models.Index(fields=["crm_contact_id", "-created_at"]),
        ]
        verbose_name = "Aktivität"
        verbose_name_plural = "Aktivitäten"

    def __str__(self):
        return f"{self.get_activity_type_display()}: {self.subject or self.description[:60]}"


# ---------------------------------------------------------------------------
# Funktionskatalog (Verticals + Sub-Funktionen)
# ---------------------------------------------------------------------------

class EntityType(models.TextChoices):
    ATS_CANDIDATE = "ats_candidate", "ATS-Kandidat"
    CRM_CONTACT = "crm_contact", "CRM-Kontakt"


class Vertical(models.Model):
    """Oberkategorie im Funktionskatalog (z.B. 'Human Resources')."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    name = models.CharField("Name", max_length=120, unique=True)
    slug = models.SlugField("Slug", max_length=120, unique=True)
    sort_order = models.PositiveSmallIntegerField("Reihenfolge", default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "catalog_vertical"
        ordering = ["sort_order", "name"]
        verbose_name = "Vertical"
        verbose_name_plural = "Verticals"

    def __str__(self):
        return self.name


class SubFunktion(models.Model):
    """Unterkategorie innerhalb eines Verticals (z.B. 'Payroll')."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    vertical = models.ForeignKey(
        Vertical,
        on_delete=models.CASCADE,
        related_name="sub_funktionen",
        verbose_name="Vertical",
    )
    name = models.CharField("Name", max_length=200)
    slug = models.SlugField("Slug", max_length=200)
    sort_order = models.PositiveSmallIntegerField("Reihenfolge", default=0)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "catalog_subfunktion"
        ordering = ["vertical", "sort_order", "name"]
        unique_together = [("vertical", "slug")]
        verbose_name = "Sub-Funktion"
        verbose_name_plural = "Sub-Funktionen"

    def __str__(self):
        return f"{self.vertical.name} → {self.name}"


class CatalogAssignment(models.Model):
    """Zuordnung einer Person (ATS-Kandidat oder CRM-Kontakt) zu Sub-Funktionen.

    Lebt in piquano_shared, referenziert Personen per UUID (kein FK cross-DB).
    Eine Zeile pro Person × Sub-Funktion. Das Vertical ergibt sich aus der Sub-Funktion.
    """

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    entity_type = models.CharField(
        max_length=20, choices=EntityType.choices,
        help_text="Typ der zugeordneten Person",
    )
    entity_id = models.UUIDField(
        help_text="UUID des Kandidaten (ATS) oder Kontakts (CRM)",
        db_index=True,
    )
    sub_funktion = models.ForeignKey(
        SubFunktion,
        on_delete=models.CASCADE,
        related_name="assignments",
        verbose_name="Sub-Funktion",
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        db_table = "catalog_assignment"
        unique_together = [("entity_type", "entity_id", "sub_funktion")]
        indexes = [
            models.Index(fields=["entity_type", "entity_id"]),
        ]
        verbose_name = "Katalog-Zuordnung"
        verbose_name_plural = "Katalog-Zuordnungen"

    def __str__(self):
        return f"{self.get_entity_type_display()} {self.entity_id} → {self.sub_funktion}"


# ---------------------------------------------------------------------------
# Email Log (zentrales Versand-Protokoll)
# ---------------------------------------------------------------------------

class EmailLogApp(models.TextChoices):
    APP = "app", "App"
    CRM = "crm", "CRM"
    ATS = "ats", "ATS"
    LMS = "lms", "LMS"
    SUPPORT = "support", "Support"
    CONTENT = "content", "Content"
    CORE = "core", "Core"
    CRON = "cron", "Cron-Agent"


class EmailLogStatus(models.TextChoices):
    SENT = "sent", "Gesendet"
    FAILED = "failed", "Fehlgeschlagen"


class EmailLog(models.Model):
    """Zentrales Protokoll aller System-E-Mails über alle Apps."""

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    app = models.CharField("App", max_length=10, choices=EmailLogApp.choices)
    email_type = models.CharField("Typ", max_length=80)
    recipient = models.EmailField("Empfänger")
    subject = models.CharField("Betreff", max_length=500)
    status = models.CharField(
        max_length=10, choices=EmailLogStatus.choices, default=EmailLogStatus.SENT,
    )
    error_message = models.TextField("Fehler", blank=True)
    body_html = models.TextField("HTML-Inhalt", blank=True)
    mailjet_message_id = models.CharField(max_length=100, blank=True)
    sent_at = models.DateTimeField("Gesendet am", auto_now_add=True)

    class Meta:
        db_table = "email_log"
        ordering = ["-sent_at"]
        indexes = [
            models.Index(fields=["-sent_at"]),
            models.Index(fields=["app", "-sent_at"]),
            models.Index(fields=["email_type", "-sent_at"]),
            models.Index(fields=["recipient", "-sent_at"]),
        ]
        verbose_name = "E-Mail-Log"
        verbose_name_plural = "E-Mail-Logs"

    def __str__(self):
        return f"{self.get_app_display()} → {self.recipient}: {self.subject[:60]}"

    @classmethod
    def log(
        cls,
        *,
        app: str,
        email_type: str,
        recipient: str,
        subject: str,
        status: str = "sent",
        error_message: str = "",
        body_html: str = "",
        mailjet_message_id: str = "",
    ):
        """Erstellt einen Log-Eintrag. Fehler werden geloggt, nie geworfen."""
        import logging

        try:
            cls.objects.using("shared").create(
                app=app,
                email_type=email_type,
                recipient=recipient,
                subject=subject,
                status=status,
                error_message=error_message,
                body_html=body_html,
                mailjet_message_id=mailjet_message_id,
            )
        except Exception as exc:
            logging.getLogger(__name__).warning(
                "EmailLog.log fehlgeschlagen: %s", exc,
            )
