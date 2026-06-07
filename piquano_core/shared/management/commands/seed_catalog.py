"""Befüllt den Funktionskatalog (Verticals + Sub-Funktionen) in piquano_shared.

Idempotent: Erstellt nur fehlende Einträge, überschreibt nichts.
Nutzung:  manage.py seed_catalog --database=shared
"""

from django.core.management.base import BaseCommand
from django.utils.text import slugify

from piquano_core.shared.models import SubFunktion, Vertical

CATALOG = {
    "General Management": [
        "Geschäftsführung / CEO",
        "Vorstand",
        "Nachfolge- & Übergangsprozesse",
        "Business Development",
        "Internationalisierung / Globalisierung",
        "Greenfield-Aufbau / Unternehmensaufbau",
        "Strategische Unternehmensplanung",
        "Merger & Acquisition",
        "Post-Merger-Integration",
        "Carve-out & Unternehmensteilverkauf",
        "Joint Ventures",
    ],
    "Finanzen & Controlling": [
        "Leitung Finance / CFO",
        "Controlling",
        "Accounting / Rechnungswesen",
        "Budgetierung & Finanzplanung",
        "Working Capital Management",
        "Liquiditätssteuerung / Cash Management",
        "Treasury",
        "Risikomanagement (Finanzbereich)",
        "IFRS",
        "US-GAAP",
        "Due Diligence",
        "Wirtschaftsprüfung / Audit",
        "Interne Revision",
        "Steuern national",
        "Steuern international",
        "Transfer Pricing",
        "Shared Services (Finance)",
        "Fast-Close-Implementierung",
        "Finanzkonsolidierung",
        "Finance im Banking-Umfeld",
        "Investitionscontrolling",
        "Forderungsmanagement / Credit Risk",
        "Profit Improvement Planning",
        "Private-Equity-Strukturen",
        "Covenant-Management",
    ],
    "Human Resources": [
        "HR-Leitung / CHRO",
        "HR Business Partner",
        "HR-Strategie & Organisationsentwicklung",
        "Recruiting & Talent Acquisition",
        "Talent Management",
        "Personalentwicklung & Training",
        "Compensation & Benefits",
        "Payroll",
        "Arbeitsrecht",
        "Betriebsrat & Tarifverhandlungen",
        "HR Shared Services / Service Center",
        "HR-Systemimplementierung / HCM",
        "Europäisches & internationales Personalmanagement",
        "HR-Outsourcing",
        "HR-Prozessoptimierung",
        "Personalbedarfsplanung & -einsatzplanung",
        "Employer Branding",
        "HR-Transformation & Reorganisation",
        "Kulturentwicklung",
    ],
    "IT-Management": [
        "IT-Leitung / CIO",
        "IT-Strategie & Governance",
        "IT-Infrastruktur & Betriebsmanagement",
        "IT-Architektur / Enterprise Architecture",
        "IT-Prozesse & Service Management",
        "Business Applications",
        "ERP / BI (inkl. SAP-Implementierungen)",
        "SAP S/4HANA Migration & Transformation",
        "Cloud Infrastructure & Collaboration",
        "Cyber Security",
        "IT Carve-in / Carve-out",
        "Digitalisierung von Geschäftsprozessen",
        "IT-Outsourcing & Vendor Management",
        "IT-Infrastruktur Migration / Rechenzentrumsverlagerung",
        "E-Commerce & Business Intelligence",
        "Agile Transformation / Agile Methoden",
        "IT-Projektmanagement",
        "CRM-Einführung / CRM-Systeme",
    ],
    "Marketing & Vertrieb": [
        "Vertriebsleitung / CSO",
        "Vertriebssteuerung & -optimierung",
        "Vertriebsaufbau & -strukturierung",
        "Key Account Management",
        "Sales Excellence",
        "B2B-Vertrieb",
        "B2C-Vertrieb",
        "Go-to-Market",
        "Marketingstrategie",
        "Kampagnenmanagement",
        "Online-Marketing / Digitales Marketing",
        "Unternehmenskommunikation",
        "Markenentwicklung",
        "Customer Service & Call Center",
        "Business Development & strategische Partnerschaften",
        "Channel Management",
    ],
    "Programm- und Projektmanagement": [
        "Projektmanagement / Projektleitung",
        "Programmmanagement",
        "PMO (Project Management Office)",
        "Multiprojektmanagement",
        "Projektplanung & -steuerung",
        "Projektsanierung / Turnaround-Projekte",
        "Agiles Projektmanagement / Scrum",
        "Technisches Projektmanagement",
        "Internationales / globales Projektmanagement",
    ],
    "Einkauf & Supply Chain": [
        "Strategischer Einkauf / CPO",
        "SCM-Prozesse & Supply Chain Optimierung",
        "Lieferantenmanagement / Supplier Development",
        "Sourcing & Ausschreibungsmanagement",
        "Category Management",
        "Materialwirtschaft / Stammdatenmanagement",
        "Outsourcing & Insourcing Management",
        "Einkaufs-Transformation & Prozessoptimierung",
        "Kostenreduktion & Spend Management",
        "Einkauf im SAP-Umfeld",
        "LkSG / Nachhaltigkeit im Einkauf",
        "Vertragsverhandlung im Einkauf",
        "Automatisierung der Beschaffungsprozesse",
    ],
    "Produktion & Operations": [
        "Produktionsleitung / COO",
        "Werkleitung",
        "Produktionsplanung & -steuerung",
        "Produktionsanlauf & Industrialisierung",
        "Produktionsverlagerung",
        "Werksschließung",
        "Lean Management / Lean Manufacturing",
        "Operations Management",
        "Effizienzsteigerung & Prozessoptimierung",
        "Anlagenplanung & Inbetriebnahme",
        "Nachhaltige Produktion",
        "Globale Multi-Site-Leitung",
    ],
    "Transformation & Change": [
        "Digitale Transformation",
        "Transformation & Change Management",
        "Organisationsentwicklung",
        "Geschäftsmodellentwicklung",
        "Optimierung & Wachstum",
        "Start-up-Aufbau / Skalierungsstrategien",
        "Contact Center Transformation",
        "Finanzprozess-Transformation",
        "IT-Transformation",
        "Prozessintegration",
    ],
    "Restrukturierung & Sanierung": [
        "Restrukturierung & Reorganisation",
        "Sanierung / Turnaround-Management",
        "Kostensenkungsprogramme",
        "Eigenverwaltung / Insolvenzbegleitung",
        "Sozialplan & Betriebsänderung",
        "Carve-out Management",
        "Krisenmanagement",
        "Liquiditätssicherung",
        "Profit Improvement / Ergebnisverbesserung",
    ],
    "Recht & Compliance": [
        "Compliance Management",
        "Regulatory Affairs",
        "Interne Revision & Governance",
        "Legal Tech & Compliance Operations",
        "Risikomanagement & Compliance",
        "EU-Taxonomie & ESG-Compliance",
        "Datenschutz / DSGVO",
    ],
    "Logistik & Warehousing": [
        "Logistiksteuerung / CLO",
        "Transport & Distribution",
        "Lager & Warehousing",
        "Zollabwicklung",
        "Internationale Logistik",
        "Zentralisierte Logistiksteuerung",
        "Logistikprozessoptimierung",
        "Outsourcing in der Logistik",
    ],
    "Engineering & Entwicklung": [
        "Ingenieurswesen / Technische Leitung",
        "Forschung & Entwicklung (R&D)",
        "Produktentwicklung & Produktmanagement",
        "Konstruktion & Entwicklungsberatung",
        "Digitalisierung von Entwicklungsprozessen",
        "Modularisierungskonzepte",
        "Industrielle Automatisierung",
        "Design Verification & Validierung",
        "Innovation & Patentierung",
        "Telekommunikations-Infrastruktur & FTTH",
        "Hydrogen & Energietransformation",
    ],
    "Qualitätsmanagement": [
        "QM-Leitung",
        "Qualitätssicherung & Qualitätskontrolle",
        "ISO 9001 / Zertifizierungsmanagement",
        "QMS-Implementierung",
        "Prozess- und Qualitätsverbesserung",
        "Pharmaceutical & MedTech Quality",
        "Qualitätsstandards international",
    ],
}


class Command(BaseCommand):
    help = "Befüllt den Funktionskatalog (idempotent)"

    def handle(self, *args, **options):
        created_v = 0
        created_sf = 0

        for v_order, (v_name, subs) in enumerate(CATALOG.items(), start=1):
            vertical, was_created = Vertical.objects.using("shared").get_or_create(
                slug=slugify(v_name),
                defaults={"name": v_name, "sort_order": v_order},
            )
            if was_created:
                created_v += 1
                self.stdout.write(f"  + Vertical: {v_name}")
            else:
                self.stdout.write(f"  = Vertical: {v_name} (existiert)")

            for sf_order, sf_name in enumerate(subs, start=1):
                _, sf_created = SubFunktion.objects.using("shared").get_or_create(
                    vertical=vertical,
                    slug=slugify(sf_name),
                    defaults={"name": sf_name, "sort_order": sf_order},
                )
                if sf_created:
                    created_sf += 1

        total_v = Vertical.objects.using("shared").count()
        total_sf = SubFunktion.objects.using("shared").count()
        self.stdout.write(
            self.style.SUCCESS(
                f"\nFertig: {created_v} Verticals neu, {created_sf} Sub-Funktionen neu. "
                f"Gesamt: {total_v} Verticals, {total_sf} Sub-Funktionen."
            )
        )
