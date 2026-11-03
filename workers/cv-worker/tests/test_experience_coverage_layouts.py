"""Experience coverage must read real missions, not headers or sidebar text.

Layouts from the test bank (2026-11-03):
- oussama: date range alone on a line, role/company on the next one, and the
  candidate first name repeated as a page header;
- hodard: two-column PDF where the sidebar (letter-spaced "D E S C R I P T I O N",
  skills, hobbies) is extracted between the missions, then "Missions (suite)".
"""
from src.structuring import extract_source_experience_coverage_items, validate_source_fidelity

DATE_ON_ITS_OWN_LINE = """
JEAN
01/2024 – Aujourd’hui
Software Engineer - CDI chez ACME - France
Missions clés
• Concevoir les API REST Spring Boot pour le portail de souscription.
• Automatiser les contrôles de qualité avec GitLab CI et SonarQube.
Environnement technique
Java, Spring Boot, GitLab CI.
JEAN
07/2022 – 01/2024
RPA Developer chez Banque Exemple - France
Missions clés
• Développer les workflows RPA conformément aux besoins exprimés.
"""

SIDEBAR_BETWEEN_MISSIONS = """
JEAN
Ingénieur DevOps / Full-Stack
De mai 2022 à août 2024
Ingénieur DevOps | ACME | Rouen
Missions
• Création d'environnements de test : tests rapides, réduction 50% des
déploiements superflus — Docker Compose, PowerShell.
JEAN
Ingénieur DevOps / Full-Stack
D E S C R I P T I O N
Programmation / Langages
• C#
• TypeScript/JavaScript
Web Infrastructure / Cloud
• HAProxy
• Velero
Centres d'intérêt
• Homelab
• guitare
Réseaux sociaux
JEAN
Missions (suite)
• Administration systèmes et réseaux : automatisation, collaboration équipe Infra — Windows, Linux.
"""


def _items(source):
    return [entry["item"] for entry in extract_source_experience_coverage_items(source, "Jean")]


def _experience(date, role, company, missions):
    return {"date": date, "role": role, "company_highlight": company,
            "sections": [{"heading": "Missions clés", "content": missions}]}


def test_date_and_role_lines_are_headers_not_missions():
    assert _items(DATE_ON_ITS_OWN_LINE) == [
        "Concevoir les API REST Spring Boot pour le portail de souscription.",
        "Automatiser les contrôles de qualité avec GitLab CI et SonarQube.",
        "Environnement technique Java, Spring Boot, GitLab CI.",
        "Développer les workflows RPA conformément aux besoins exprimés.",
    ]


def test_sidebar_is_not_read_as_missions_and_continued_missions_are():
    assert _items(SIDEBAR_BETWEEN_MISSIONS) == [
        "Création d'environnements de test : tests rapides, réduction 50% des déploiements superflus — Docker Compose, PowerShell.",
        "Administration systèmes et réseaux : automatisation, collaboration équipe Infra — Windows, Linux.",
    ]


def _faithful_cv():
    return {
        "name": "JEAN",
        "title": "Software Engineer",
        "formations": [],
        "skills": [{"category": "Outils", "items": ["Java", "Spring Boot", "GitLab CI"]}],
        "experiences": [
            _experience("01/2024 – Aujourd’hui", "Software Engineer - CDI", "ACME - France", [
                "Concevoir les API REST Spring Boot pour le portail de souscription.",
                "Automatiser les contrôles de qualité avec GitLab CI et SonarQube.",
                "Environnement technique : Java, Spring Boot, GitLab CI.",
            ]),
            _experience("07/2022 – 01/2024", "RPA Developer", "Banque Exemple - France", [
                "Développer les workflows RPA conformément aux besoins exprimés.",
            ]),
        ],
    }


def _coverage_codes(data):
    return [w["code"] for w in data.get("_fidelity_soft_warnings") or [] if w["code"].startswith("source_coverage")]


def test_faithful_split_header_cv_has_no_coverage_warning():
    data = _faithful_cv()

    validate_source_fidelity(DATE_ON_ITS_OWN_LINE, data, forbidden_identity_terms=[])

    assert _coverage_codes(data) == []


def test_dropped_mission_is_still_reported():
    data = _faithful_cv()
    data["experiences"][0]["sections"][0]["content"].pop(1)

    validate_source_fidelity(DATE_ON_ITS_OWN_LINE, data, forbidden_identity_terms=[])

    assert _coverage_codes(data) == ["source_coverage_missing_experience_item"]
    assert "GitLab CI et SonarQube" in data["_fidelity_soft_warnings"][0]["message"]


def test_dropped_mission_after_sidebar_is_still_reported():
    data = {
        "name": "JEAN", "title": "Ingénieur DevOps / Full-Stack", "formations": [],
        "skills": [{"category": "Langages", "items": ["C#", "TypeScript/JavaScript", "HAProxy", "Velero"]}],
        "experiences": [_experience("De mai 2022 à août 2024", "Ingénieur DevOps", "ACME | Rouen", [
            "Création d'environnements de test : tests rapides, réduction 50% des déploiements superflus — Docker Compose, PowerShell.",
        ])],
    }

    validate_source_fidelity(SIDEBAR_BETWEEN_MISSIONS, data, forbidden_identity_terms=[])

    messages = [w["message"] for w in data["_fidelity_soft_warnings"] if w["code"] == "source_coverage_missing_experience_item"]
    assert len(messages) == 1 and "Administration systèmes et réseaux" in messages[0]


def test_mission_cut_by_a_page_header_keeps_its_continuation():
    source = """
JEAN
Missions
• Mise en place de la supervision Prometheus et des alertes pour
JEAN
Ingénieur DevOps / Full-Stack
les équipes produit et sécurité.
"""

    assert _items(source) == [
        "Mise en place de la supervision Prometheus et des alertes pour les équipes produit et sécurité.",
    ]


def test_continued_business_section_heading_starts_a_new_section():
    from src.structuring import extract_source_business_coverage_facts

    source = """
Langues
• Anglais : Bilingue
Autres — suite
• Gestion de projet agile et animation des rituels Scrum
E X P É R I E N C E S   P R O F E S S I O N N E L L E S
De mai 2022 à août 2024
"""

    facts = extract_source_business_coverage_facts(source)

    assert {"section": "Langues", "fact": "Anglais : Bilingue"} in facts
    assert not any("suite" in f["fact"] or "E X P" in f["fact"] for f in facts)


def test_labelled_field_line_starts_a_new_item():
    source = """
Missions
• Déploiement en homologation
Environnement fonctionnel : Middle-Office, Pricing, Back-Office
"""

    assert _items(source) == [
        "Déploiement en homologation",
        "Environnement fonctionnel : Middle-Office, Pricing, Back-Office",
    ]
