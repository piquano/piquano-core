"""
Default-Registrierungen fuer alle Piquano-Apps.

Wird beim Import automatisch in die Registry eingetragen.
"""

from __future__ import annotations

from .registry import register_app

APP_LABELS = {
    "crm": "Piquano CRM",
    "ats": "Piquano ATS",
    "app": "Piquano Hub",
    "lms": "Piquano LMS",
    "ticket": "Piquano Ticketsystem",
    "content": "Piquano Content Studio",
}

MODULE_LABELS = {
    # CRM
    "crm.contacts": "Kontakte",
    "crm.deals": "Deals & Pipeline",
    "crm.activities": "Aktivitäten",
    "crm.emails": "E-Mail-Kampagnen",
    "crm.briefings": "Briefings",
    "crm.reports": "Berichte",
    "crm.workflows": "Workflows",
    "crm.integrations": "Integrationen",
    "crm.ms365": "Microsoft 365 Mail-Sync",
    "crm.timeline": "Timeline",
    "crm.accounts": "Benutzerverwaltung",
    "crm.projektabrechnung": "Projektabrechnung",
    "crm.partner_pipeline": "Partner-Pipeline",
    # ATS
    "ats.candidates": "Kandidaten",
    "ats.jobs": "Projekte & Ausschreibungen",
    "ats.careers": "Karriereseite",
    "ats.mail": "E-Mail-Postfach",
    "ats.mail_templates": "E-Mail-Vorlagen",
    "ats.reports": "Berichte",
    "ats.pipeline": "Pipeline-Board",
    # App
    "app.partners": "Partner-Profile",
    "app.casestudies": "Case Studies",
    "app.wettbewerb": "Wettbewerbsanalyse",
    "app.ki_beitrag": "KI-Beiträge",
    "app.linkedin_review": "LinkedIn-Review",
    "app.vertriebscoach": "Vertriebscoach",
    "app.onboarding": "Onboarding",
    "app.personalakte": "Partnerakte",
    "app.activities": "Aktivitäten",
    "app.opportunities": "Opportunity Pipeline",
    # LMS
    "lms.courses": "Kurse",
    "lms.lessons": "Lektionen",
    "lms.enrollments": "Einschreibungen",
    "lms.certificates": "Zertifikate",
    "lms.progress": "Fortschritt",
    # Ticket
    "ticket.tickets": "Tickets",
    "ticket.comments": "Kommentare",
    "ticket.categories": "Kategorien",
    "ticket.assignments": "Zuweisungen",
    "ticket.reports": "Berichte",
    # Content
    "content.dashboard": "Dashboard",
    "content.posts": "Posts & Pipeline",
    "content.calendar": "Kalender",
    "content.templates": "Vorlagen",
    "content.linkedin": "LinkedIn-Integration",
    "content.analytics": "Auswertung",
}

PERMISSION_LABELS = {
    "read": "Lesen",
    "write": "Bearbeiten",
    "delete": "Löschen",
}

PIQUANO_APP_REGISTRY: dict[str, dict[str, list[str]]] = {
    "crm": {
        "contacts": ["read", "write", "delete"],
        "deals": ["read", "write", "delete"],
        "activities": ["read", "write"],
        "emails": ["read", "write"],
        "briefings": ["read", "write"],
        "reports": ["read"],
        "workflows": ["read", "write"],
        "integrations": ["read", "write"],
        "ms365": ["read", "write"],
        "timeline": ["read"],
        "accounts": ["read", "write", "delete"],
        "projektabrechnung": ["read", "write"],
        "partner_pipeline": ["read"],
    },
    "ats": {
        "candidates": ["read", "write", "delete"],
        "jobs": ["read", "write", "delete"],
        "careers": ["read", "write"],
        "mail": ["read", "write"],
        "mail_templates": ["read", "write"],
        "reports": ["read"],
        "pipeline": ["read", "write"],
    },
    "app": {
        "partners": ["read", "write"],
        "casestudies": ["read", "write", "delete"],
        "wettbewerb": ["read", "write"],
        "ki_beitrag": ["read", "write"],
        "linkedin_review": ["read", "write"],
        "vertriebscoach": ["read"],
        "activities": ["read"],
        "opportunities": ["read", "write"],
    },
    "lms": {
        "courses": ["read", "write", "delete"],
        "lessons": ["read", "write", "delete"],
        "enrollments": ["read", "write"],
        "certificates": ["read", "write"],
        "progress": ["read"],
    },
    "ticket": {
        "tickets": ["read", "write", "delete"],
        "comments": ["read", "write"],
        "categories": ["read", "write"],
        "assignments": ["read", "write"],
        "reports": ["read"],
    },
    "content": {
        "dashboard": ["read"],
        "posts": ["read", "write", "delete"],
        "calendar": ["read"],
        "templates": ["read", "write"],
        "linkedin": ["read", "write"],
        "analytics": ["read"],
    },
}

# Register all apps on import
for _app_label, _modules in PIQUANO_APP_REGISTRY.items():
    register_app(_app_label, _modules)
