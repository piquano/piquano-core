"""Migriert bestehende verticals/mailjet_funktionen/schwerpunkte auf den neuen Katalog.

Idempotent: Erstellt nur fehlende Zuordnungen, überschreibt nichts.
Rollback-fähig: Alte Felder werden nicht verändert.

Nutzung:
  manage.py migrate_to_catalog --dry-run          # Nur analysieren
  manage.py migrate_to_catalog                    # Migrieren
  manage.py migrate_to_catalog --entity-type=ats  # Nur ATS-Kandidaten
  manage.py migrate_to_catalog --entity-type=crm  # Nur CRM-Kontakte
"""

import logging

from django.core.management.base import BaseCommand
from django.utils.text import slugify

from piquano_core.shared.models import (
    CatalogAssignment,
    EntityType,
    SubFunktion,
    Vertical,
)

logger = logging.getLogger("piquano")

# Mapping: alte Vertical-Slugs (Job-basiert) → neuer Katalog-Slug
VERTICAL_SLUG_MAP = {
    "executives-und-c-level-1": "general-management",
    "finanzen-controlling-1": "finanzen-controlling",
    "human-resources-1": "human-resources",
    "informationstechnologie-1": "it-management",
    "marketing-vertrieb-1": "marketing-vertrieb",
    "programm-und-projektmanagement-1": "programm-und-projektmanagement",
    "einkauf-und-supply-chain-management-1": "einkauf-supply-chain",
    "produktion-operations-1": "produktion-operations",
    "transformation-change-1": "transformation-change",
    "restrukturierung-1": "restrukturierung-sanierung",
}

# Mapping: mailjet_funktionen-Werte → (vertical_slug, subfunktion_slug)
# Nur die häufigsten ~80 Werte, Rest wird per Fuzzy-Match oder ignoriert
FUNKTIONEN_MAP = {
    # General Management
    "Geschäftsführung": ("general-management", "geschaftsfuhrung-ceo"),
    "General Management": ("general-management", "general-management"),
    "Vakanzüberbrückung": ("general-management", "nachfolge-ubergangsprozesse"),
    "Nachfolge- & Übergangsprozesse": ("general-management", "nachfolge-ubergangsprozesse"),
    "Internationalisierung": ("general-management", "internationalisierung-globalisierung"),
    "Post-Merger-Integration": ("general-management", "post-merger-integration"),
    # Finanzen & Controlling
    "Finance allgemein": ("finanzen-controlling", "leitung-finance-cfo"),
    "Finanzen": ("finanzen-controlling", "leitung-finance-cfo"),
    "Controlling": ("finanzen-controlling", "controlling"),
    "Controlling allgemein": ("finanzen-controlling", "controlling"),
    "Due Diligence": ("finanzen-controlling", "due-diligence"),
    "Investitionscontrolling": ("finanzen-controlling", "investitionscontrolling"),
    # Human Resources
    "Human Resources": ("human-resources", "hr-leitung-chro"),
    "HR Leitung": ("human-resources", "hr-leitung-chro"),
    "HR Projekte": ("human-resources", "hr-strategie-organisationsentwicklung"),
    "Payroll": ("human-resources", "payroll"),
    "Recruiting": ("human-resources", "recruiting-talent-acquisition"),
    "Employer Branding": ("human-resources", "employer-branding"),
    # IT-Management
    "Informationstechnologie": ("it-management", "it-leitung-cio"),
    "IT Infrastruktur": ("it-management", "it-infrastruktur-betriebsmanagement"),
    "SAP": ("it-management", "erp-bi-inkl-sap-implementierungen"),
    "ERP": ("it-management", "erp-bi-inkl-sap-implementierungen"),
    "Digitalisierung": ("it-management", "digitalisierung-von-geschaftsprozessen"),
    "Cyber Security": ("it-management", "cyber-security"),
    # Marketing & Vertrieb
    "Marketing": ("marketing-vertrieb", "marketingstrategie"),
    "Marketingstrategie": ("marketing-vertrieb", "marketingstrategie"),
    "Vertrieb": ("marketing-vertrieb", "vertriebsleitung-cso"),
    "Vertriebssteuerung": ("marketing-vertrieb", "vertriebssteuerung-optimierung"),
    "Vertriebsoptimierung": ("marketing-vertrieb", "vertriebssteuerung-optimierung"),
    "Vertriebsleitung": ("marketing-vertrieb", "vertriebsleitung-cso"),
    "Key Account Management": ("marketing-vertrieb", "key-account-management"),
    "Online Marketing": ("marketing-vertrieb", "online-marketing-digitales-marketing"),
    # Programm- und Projektmanagement
    "Projektmanagement": ("programm-und-projektmanagement", "projektmanagement-projektleitung"),
    "Programm- und Projektmanagement": ("programm-und-projektmanagement", "programmmanagement"),
    "Projektleitung": ("programm-und-projektmanagement", "projektmanagement-projektleitung"),
    "PMO": ("programm-und-projektmanagement", "pmo-project-management-office"),
    "Projektplanung": ("programm-und-projektmanagement", "projektplanung-steuerung"),
    "Projektsanierung": ("programm-und-projektmanagement", "projektsanierung-turnaround-projekte"),
    "Time-to-market": ("programm-und-projektmanagement", "projektplanung-steuerung"),
    # Einkauf & Supply Chain
    "Supply Chain Management": ("einkauf-supply-chain", "scm-prozesse-supply-chain-optimierung"),
    "SCM-Prozesse": ("einkauf-supply-chain", "scm-prozesse-supply-chain-optimierung"),
    "Einkauf": ("einkauf-supply-chain", "strategischer-einkauf-cpo"),
    "Strategischer Einkauf": ("einkauf-supply-chain", "strategischer-einkauf-cpo"),
    "Lieferantenmanagement": ("einkauf-supply-chain", "lieferantenmanagement-supplier-development"),
    # Produktion & Operations
    "Produktionssteuerung": ("produktion-operations", "produktionsplanung-steuerung"),
    "Ingenieurswesen und Produktion": ("produktion-operations", "produktionsleitung-coo"),
    "Produktion": ("produktion-operations", "produktionsleitung-coo"),
    "Produktionsplanung": ("produktion-operations", "produktionsplanung-steuerung"),
    "Lean Management": ("produktion-operations", "lean-management-lean-manufacturing"),
    "Produktionsverlagerung": ("produktion-operations", "produktionsverlagerung"),
    "Operations Management": ("produktion-operations", "operations-management"),
    # Transformation & Change
    "Transformation": ("transformation-change", "transformation-change-management"),
    "Transformation und Change": ("transformation-change", "transformation-change-management"),
    "Transformation & Change": ("transformation-change", "transformation-change-management"),
    "Change Management": ("transformation-change", "transformation-change-management"),
    "Optimierung & Wachstum": ("transformation-change", "optimierung-wachstum"),
    "Digitale Transformation": ("transformation-change", "digitale-transformation"),
    "Organisationsentwicklung": ("transformation-change", "organisationsentwicklung"),
    # Restrukturierung & Sanierung
    "Restrukturierung": ("restrukturierung-sanierung", "restrukturierung-reorganisation"),
    "Restrukturierung & Reorganisation": ("restrukturierung-sanierung", "restrukturierung-reorganisation"),
    "Turnaround": ("restrukturierung-sanierung", "sanierung-turnaround-management"),
    "Krisenmanagement": ("restrukturierung-sanierung", "krisenmanagement"),
    "Kostensenkung": ("restrukturierung-sanierung", "kostensenkungsprogramme"),
    # Logistik
    "Logistik": ("logistik-warehousing", "logistiksteuerung-clo"),
    "Zollabwicklung": ("logistik-warehousing", "zollabwicklung"),
    # Qualität
    "Qualitätsmanagement": ("qualitatsmanagement", "qm-leitung"),
    # --- Zusätzliche Mappings (aus Dry-Run) ---
    # General Management
    "Business Development": ("general-management", "business-development"),
    "Executives & C-Level": ("general-management", "geschaftsfuhrung-ceo"),
    "Globalisierung": ("general-management", "internationalisierung-globalisierung"),
    "Greenfield": ("general-management", "greenfield-aufbau-unternehmensaufbau"),
    "Merger & Acquisition": ("general-management", "merger-acquisition"),
    "Post Merger": ("general-management", "post-merger-integration"),
    "PMI": ("general-management", "post-merger-integration"),
    # Finanzen & Controlling
    "Accounting allgemein": ("finanzen-controlling", "accounting-rechnungswesen"),
    "Audit": ("finanzen-controlling", "wirtschaftsprufung-audit"),
    "Wirtschaftsprüfung": ("finanzen-controlling", "wirtschaftsprufung-audit"),
    "Due Dilligence": ("finanzen-controlling", "due-diligence"),
    "Finance - Banking": ("finanzen-controlling", "finance-im-banking-umfeld"),
    "Finance - Risikomanagement": ("finanzen-controlling", "risikomanagement-finanzbereich"),
    "Finanzen und Controlling": ("finanzen-controlling", "controlling"),
    "IFRS": ("finanzen-controlling", "ifrs"),
    "US-GAAP": ("finanzen-controlling", "us-gaap"),
    "Steuern": ("finanzen-controlling", "steuern-national"),
    "Steuern International": ("finanzen-controlling", "steuern-international"),
    "Working Capital": ("finanzen-controlling", "working-capital-management"),
    "Shared Services": ("finanzen-controlling", "shared-services-finance"),
    # Human Resources
    "HR Business Partner": ("human-resources", "hr-business-partner"),
    "HR Strategie": ("human-resources", "hr-strategie-organisationsentwicklung"),
    "Arbeitsrecht": ("human-resources", "arbeitsrecht"),
    "Betriebsrat": ("human-resources", "betriebsrat-tarifverhandlungen"),
    "Talent Management": ("human-resources", "talent-management"),
    "Sourcing, Recruiting & Retention": ("human-resources", "recruiting-talent-acquisition"),
    "Sozialplan": ("restrukturierung-sanierung", "sozialplan-betriebsanderung"),
    # IT-Management
    "IT Strategie": ("it-management", "it-strategie-governance"),
    "IT Architektur": ("it-management", "it-architektur-enterprise-architecture"),
    "IT Prozesse": ("it-management", "it-prozesse-service-management"),
    "IT Carve-in/-out": ("it-management", "it-carve-in-carve-out"),
    "Business Applications": ("it-management", "business-applications"),
    "Cloud Infrastructure": ("it-management", "cloud-infrastructure-collaboration"),
    "CRM": ("it-management", "crm-einfuhrung-crm-systeme"),
    "CRM-Einführung": ("it-management", "crm-einfuhrung-crm-systeme"),
    "ERP/BI": ("it-management", "erp-bi-inkl-sap-implementierungen"),
    "SAP FI/CO": ("it-management", "erp-bi-inkl-sap-implementierungen"),
    "SAP Migration & Transformation": ("it-management", "sap-s4hana-migration-transformation"),
    "SAP S/4HANA - Finance": ("it-management", "sap-s4hana-migration-transformation"),
    "SAP S/4HANA - Supply Chain / Sourcing": ("it-management", "sap-s4hana-migration-transformation"),
    "SAP S/4HANA - allgemein": ("it-management", "sap-s4hana-migration-transformation"),
    # Marketing & Vertrieb
    "Sales": ("marketing-vertrieb", "vertriebsleitung-cso"),
    "Sales Excellence": ("marketing-vertrieb", "sales-excellence"),
    "B2B": ("marketing-vertrieb", "b2b-vertrieb"),
    "B2C": ("marketing-vertrieb", "b2c-vertrieb"),
    "Go-to-market": ("marketing-vertrieb", "go-to-market"),
    "Kampagnenmanagement": ("marketing-vertrieb", "kampagnenmanagement"),
    "Online-Marketing": ("marketing-vertrieb", "online-marketing-digitales-marketing"),
    "Unternehmenskommunikation": ("marketing-vertrieb", "unternehmenskommunikation"),
    "Markensanierung": ("marketing-vertrieb", "markenentwicklung"),
    "Customer Service": ("marketing-vertrieb", "customer-service-call-center"),
    "Call Center": ("marketing-vertrieb", "customer-service-call-center"),
    "Umsatzsteigerung": ("marketing-vertrieb", "vertriebssteuerung-optimierung"),
    "Vertrieb Restrukturierung": ("marketing-vertrieb", "vertriebsaufbau-strukturierung"),
    # Programm- und Projektmanagement
    "Scrum": ("programm-und-projektmanagement", "agiles-projektmanagement-scrum"),
    "Projektassistenz": ("programm-und-projektmanagement", "projektmanagement-projektleitung"),
    "Projekt": ("programm-und-projektmanagement", "projektmanagement-projektleitung"),
    # Einkauf & Supply Chain
    "Einkauf & SCM": ("einkauf-supply-chain", "strategischer-einkauf-cpo"),
    "SCM": ("einkauf-supply-chain", "scm-prozesse-supply-chain-optimierung"),
    "Supplier Management": ("einkauf-supply-chain", "lieferantenmanagement-supplier-development"),
    "Outsourcing": ("einkauf-supply-chain", "outsourcing-insourcing-management"),
    "Insourcing": ("einkauf-supply-chain", "outsourcing-insourcing-management"),
    "Wertschöpfungskette": ("einkauf-supply-chain", "scm-prozesse-supply-chain-optimierung"),
    # Produktion & Operations
    "Produktion und Operations": ("produktion-operations", "produktionsleitung-coo"),
    "Produktionsleitung": ("produktion-operations", "produktionsleitung-coo"),
    "Produktionsanlauf": ("produktion-operations", "produktionsanlauf-industrialisierung"),
    "Operations": ("produktion-operations", "operations-management"),
    "Werkleitung": ("produktion-operations", "werkleitung"),
    "Werksschließung": ("produktion-operations", "werksschliessung"),
    "Effizienzsteigerung": ("produktion-operations", "effizienzsteigerung-prozessoptimierung"),
    "Prozessoptimierung": ("produktion-operations", "effizienzsteigerung-prozessoptimierung"),
    # Restrukturierung & Sanierung
    "Sanierung": ("restrukturierung-sanierung", "sanierung-turnaround-management"),
    "Kostensenkung": ("restrukturierung-sanierung", "kostensenkungsprogramme"),
    "Eigenverwaltung": ("restrukturierung-sanierung", "eigenverwaltung-insolvenzbegleitung"),
    "Veränderungs- & Krisenkommunikation": ("restrukturierung-sanierung", "krisenmanagement"),
    # Recht & Compliance
    "Compliance": ("recht-compliance", "compliance-management"),
    # Logistik
    "Logstik & Transport": ("logistik-warehousing", "transport-distribution"),
    # Engineering & Entwicklung
    "Ingenieurswesen": ("engineering-entwicklung", "ingenieurswesen-technische-leitung"),
    "F&E": ("engineering-entwicklung", "forschung-entwicklung-rd"),
    "Forschung & Entwicklung": ("engineering-entwicklung", "forschung-entwicklung-rd"),
    "Produktmanagement": ("engineering-entwicklung", "produktentwicklung-produktmanagement"),
    "Sensortechnik": ("engineering-entwicklung", "industrielle-automatisierung"),
    "Environment, Health and Safety (EHS)": ("qualitatsmanagement", "qm-leitung"),
    # Qualitätsmanagement
    "Qualitätsmanagement (QM)": ("qualitatsmanagement", "qm-leitung"),
    # --- Zusätzliche Mappings (aus Prod Dry-Run) ---
    "Agile Methoden": ("programm-und-projektmanagement", "agiles-projektmanagement-scrum"),
    "Cloud Infrastructure & Collaboration": ("it-management", "cloud-infrastructure-collaboration"),
    "Compensation&Benefits": ("human-resources", "compensation-benefits"),
    "Executive": ("general-management", "geschaftsfuhrung-ceo"),
    "Finance": ("finanzen-controlling", "leitung-finance-cfo"),
    "Finanzen Steuern International": ("finanzen-controlling", "steuern-international"),
    "Lager & Distribution": ("logistik-warehousing", "lager-warehousing"),
    "Marketing & Vertrieb": ("marketing-vertrieb", "vertriebsleitung-cso"),
    "Multiprojektmanagement": ("programm-und-projektmanagement", "multiprojektmanagement"),
    "Produktion & Operations": ("produktion-operations", "produktionsleitung-coo"),
    "Programm-Management": ("programm-und-projektmanagement", "programmmanagement"),
    "Projektsteuerung": ("programm-und-projektmanagement", "projektplanung-steuerung"),
    "Rechnungswesen": ("finanzen-controlling", "accounting-rechnungswesen"),
    "Retention Talent Management": ("human-resources", "talent-management"),
    "Sourcing": ("einkauf-supply-chain", "sourcing-ausschreibungsmanagement"),
    "Transport": ("logistik-warehousing", "transport-distribution"),
    "Treasury": ("finanzen-controlling", "treasury"),
    "Turnaround-Projekte": ("programm-und-projektmanagement", "projektsanierung-turnaround-projekte"),
    "Vertriebsaufbau": ("marketing-vertrieb", "vertriebsaufbau-strukturierung"),
    "Wachstum Transformation": ("transformation-change", "optimierung-wachstum"),
    # Sonstige — ignorieren
    "Interim Manager": None,
    "Administration": None,
    "Andere": None,
    "Pool": None,
    "allgemeiner Managerpool": None,
}


# Alle bekannten Funktionsnamen — für Fuzzy-Split von CRM Dirty Data
_KNOWN_FUNKTIONEN = sorted(FUNKTIONEN_MAP.keys(), key=len, reverse=True)


def _split_dirty_value(raw):
    """Splittet einen verschmutzten CRM-String in bekannte Funktionsnamen.

    CRM-Daten haben oft fehlende Semikolons, z.B.:
    "Accounting allgemein Administration PMO Projektmanagement"
    → ["Accounting allgemein", "Administration", "PMO", "Projektmanagement"]
    """
    if not raw:
        return []

    # Erst nach Semikolon splitten
    parts = []
    for segment in raw.split(";"):
        segment = segment.strip()
        if not segment:
            continue
        # Komma-Split
        for sub in segment.split(","):
            sub = sub.strip()
            if sub:
                parts.append(sub)

    results = []
    for part in parts:
        # Wenn der Teil ein bekannter Funktionsname ist, direkt nehmen
        if part in FUNKTIONEN_MAP:
            results.append(part)
            continue

        # Sonst: Greedy-Match bekannter Namen aus dem String herausschneiden
        remaining = part
        matched_any = False
        for known in _KNOWN_FUNKTIONEN:
            if known in remaining:
                results.append(known)
                remaining = remaining.replace(known, "", 1).strip()
                matched_any = True

        # Falls nichts gematcht, den Original-Wert behalten (wird als unmapped gemeldet)
        if not matched_any and remaining:
            results.append(part)

    return results


class Command(BaseCommand):
    help = "Migriert bestehende Kategorisierungen auf den neuen Funktionskatalog"

    def add_arguments(self, parser):
        parser.add_argument(
            "--dry-run",
            action="store_true",
            help="Nur analysieren, keine Änderungen",
        )
        parser.add_argument(
            "--entity-type",
            choices=["ats", "crm"],
            help="Nur ATS-Kandidaten oder CRM-Kontakte migrieren",
        )

    def handle(self, *args, **options):
        dry_run = options["dry_run"]
        entity_filter = options.get("entity_type")

        # Katalog laden
        verticals_by_slug = {
            v.slug: v for v in Vertical.objects.using("shared").all()
        }
        subfunktionen_by_key = {}
        for sf in SubFunktion.objects.using("shared").select_related("vertical").all():
            subfunktionen_by_key[(sf.vertical.slug, sf.slug)] = sf

        stats = {
            "verticals_mapped": 0,
            "funktionen_mapped": 0,
            "funktionen_unmapped": set(),
            "assignments_created": 0,
            "assignments_skipped": 0,
        }

        if entity_filter in (None, "ats"):
            self._migrate_ats(verticals_by_slug, subfunktionen_by_key, stats, dry_run)

        if entity_filter in (None, "crm"):
            self._migrate_crm(verticals_by_slug, subfunktionen_by_key, stats, dry_run)

        # Report
        prefix = "[DRY-RUN] " if dry_run else ""
        self.stdout.write(f"\n{prefix}=== Ergebnis ===")
        self.stdout.write(f"  Vertical-Zuordnungen gemappt: {stats['verticals_mapped']}")
        self.stdout.write(f"  Funktionen gemappt: {stats['funktionen_mapped']}")
        self.stdout.write(f"  Assignments erstellt: {stats['assignments_created']}")
        self.stdout.write(f"  Assignments übersprungen (existieren): {stats['assignments_skipped']}")
        if stats["funktionen_unmapped"]:
            self.stdout.write(
                self.style.WARNING(
                    f"  Nicht gemappt ({len(stats['funktionen_unmapped'])} Werte):"
                )
            )
            for val in sorted(stats["funktionen_unmapped"]):
                self.stdout.write(f"    - {val}")

    def _assign(self, entity_type, entity_id, sub_funktion, stats, dry_run):
        if dry_run:
            stats["assignments_created"] += 1
            return
        _, created = CatalogAssignment.objects.using("shared").get_or_create(
            entity_type=entity_type,
            entity_id=entity_id,
            sub_funktion=sub_funktion,
        )
        if created:
            stats["assignments_created"] += 1
        else:
            stats["assignments_skipped"] += 1

    def _map_vertical_slug(self, old_slug, verticals_by_slug, subfunktionen_by_key):
        """Mappt einen alten Vertical-Slug auf eine Leitungs-SubFunktion."""
        new_slug = VERTICAL_SLUG_MAP.get(old_slug)
        if not new_slug or new_slug not in verticals_by_slug:
            return None
        # Erste Sub-Funktion des Verticals (typischerweise die Leitungsfunktion)
        vertical = verticals_by_slug[new_slug]
        first_sf = (
            SubFunktion.objects.using("shared")
            .filter(vertical=vertical)
            .order_by("sort_order")
            .first()
        )
        return first_sf

    def _map_funktion(self, value, subfunktionen_by_key):
        """Mappt einen mailjet_funktionen-Wert auf eine Sub-Funktion."""
        mapping = FUNKTIONEN_MAP.get(value)
        if mapping is None:
            return None  # Explizit ignoriert (z.B. "Interim Manager")
        if mapping:
            return subfunktionen_by_key.get(mapping)
        return None

    def _migrate_ats(self, verticals_by_slug, subfunktionen_by_key, stats, dry_run):
        """Migriert ATS-Kandidaten."""
        try:
            from candidates.models import Candidate
        except ImportError:
            self.stdout.write("ATS-Models nicht verfügbar, überspringe ATS-Migration")
            return

        self.stdout.write("\n--- ATS-Kandidaten ---")
        candidates = Candidate.objects.only(
            "id", "verticals", "mailjet_funktionen", "schwerpunkte"
        )

        for c in candidates.iterator(chunk_size=500):
            # 1. Alte Verticals mappen
            if c.verticals:
                for old_slug in c.verticals:
                    sf = self._map_vertical_slug(old_slug, verticals_by_slug, subfunktionen_by_key)
                    if sf:
                        self._assign(EntityType.ATS_CANDIDATE, c.id, sf, stats, dry_run)
                        stats["verticals_mapped"] += 1

            # 2. mailjet_funktionen mappen
            if c.mailjet_funktionen:
                for val in c.mailjet_funktionen.split(";"):
                    val = val.strip()
                    if not val:
                        continue
                    sf = self._map_funktion(val, subfunktionen_by_key)
                    if sf:
                        self._assign(EntityType.ATS_CANDIDATE, c.id, sf, stats, dry_run)
                        stats["funktionen_mapped"] += 1
                    elif val not in FUNKTIONEN_MAP:
                        stats["funktionen_unmapped"].add(val)

        count = candidates.count()
        self.stdout.write(f"  {count} Kandidaten verarbeitet")

    def _migrate_crm(self, verticals_by_slug, subfunktionen_by_key, stats, dry_run):
        """Migriert CRM-Kontakte."""
        try:
            from contacts.models import Contact
        except ImportError:
            self.stdout.write("CRM-Models nicht verfügbar, überspringe CRM-Migration")
            return

        self.stdout.write("\n--- CRM-Kontakte ---")
        contacts = Contact.objects.only(
            "id", "verticals", "mailjet_funktionen"
        )

        for c in contacts.iterator(chunk_size=500):
            # 1. Alte Verticals mappen (CRM speichert Labels, nicht Slugs)
            if c.verticals:
                for label in c.verticals:
                    # CRM verticals sind Labels wie "Human Resources"
                    slug = slugify(label)
                    # Versuche direkt im neuen Katalog zu finden
                    if slug in verticals_by_slug:
                        vertical = verticals_by_slug[slug]
                        first_sf = (
                            SubFunktion.objects.using("shared")
                            .filter(vertical=vertical)
                            .order_by("sort_order")
                            .first()
                        )
                        if first_sf:
                            self._assign(EntityType.CRM_CONTACT, c.id, first_sf, stats, dry_run)
                            stats["verticals_mapped"] += 1

            # 2. mailjet_funktionen mappen (CRM hat Dirty Data — Fuzzy-Split)
            if c.mailjet_funktionen:
                for val in _split_dirty_value(c.mailjet_funktionen):
                    sf = self._map_funktion(val, subfunktionen_by_key)
                    if sf:
                        self._assign(EntityType.CRM_CONTACT, c.id, sf, stats, dry_run)
                        stats["funktionen_mapped"] += 1
                    elif val not in FUNKTIONEN_MAP:
                        stats["funktionen_unmapped"].add(val)

        count = contacts.count()
        self.stdout.write(f"  {count} Kontakte verarbeitet")
