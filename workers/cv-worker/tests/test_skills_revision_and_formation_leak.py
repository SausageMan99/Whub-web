"""Request 7aaaa48c "Test-Clément" (2026-11-03), source Sanitizer_contact_strip.

1. Skills revision comments had no effect: the source skills were merged and
   the source coverage facts reinjected over the model's answer.
2. The formations sidebar, read between the skills lines, leaked into the
   `Projets` coverage fact; "plateforme Th@Bot" was dropped for its "@"; and
   no check reported it.
"""
from __future__ import annotations

import json

import fitz

from src.qa import find_pdf_source_fidelity_issues
from src.structuring import (
    REVISION_REMOVED_SOURCE_FACTS_KEY,
    build_whub_json,
    extract_source_business_coverage_facts,
)

# Text order of the two-column source: the formations sidebar is read between
# the skills lines.
SOURCE = """JEAN
Chef de projet Data et Cloud
D E S C R I P T I O N
F O R M A T I O N S
Chef de projet Data et Cloud avec 8 ans d'expérience dans la transformation
numérique.
D I P L Ô M E S
C O M P É T E N C E S   T E C H N I Q U E S
2016
Master Management des
Systèmes d'Information
IAE Paris
Compétences
• Gestion de projet: Scrum, Kanban, planning, budget, risques
• DevOps: GitHub Actions, Docker, Kubernetes, Jenkins
Projets
• plateforme Th@Bot
• API REST Node.js
2014
Licence Informatique
Université Paris Cité
E X P É R I E N C E S   P R O F E S S I O N N E L L E S
Janvier 2022 - Mars 2026
Chef de projet Data | GROUPE ATLAS | Paris (75)
Missions
• Pilotage du programme de migration cloud AWS pour les applications décisionnelles.
• Animation des comités hebdomadaires et reporting exécutif.
"""

MODEL_BASE = {
    "name": "JEAN",
    "title": "Chef de projet Data et Cloud",
    "formations": [
        {"date": "2016", "degree": "Master Management des Systèmes d'Information", "school": "IAE Paris"},
        {"date": "2014", "degree": "Licence Informatique", "school": "Université Paris Cité"},
    ],
    "experiences": [
        {
            "date": "Janvier 2022 - Mars 2026",
            "role": "Chef de projet Data | GROUPE ATLAS | Paris (75)",
            "company_highlight": "GROUPE ATLAS",
            "sections": [
                {
                    "heading": "Missions",
                    "content": [
                        "Pilotage du programme de migration cloud AWS pour les applications décisionnelles.",
                        "Animation des comités hebdomadaires et reporting exécutif.",
                    ],
                }
            ],
        }
    ],
}
MODEL_SKILLS_WITHOUT_PROJECTS = [
    {"category": "Méthodologies", "items": ["Scrum", "Kanban"]},
    {"category": "Cloud & DevOps", "items": ["GitHub Actions", "Docker", "Kubernetes", "Jenkins"]},
]
REMOVE_PROJECTS_COMMENT = {
    "comment_type": "revision",
    "body": "Dans Compétences, supprime la catégorie Projets : « 2014 Licence Informatique Université Paris Cité » est une formation, pas une compétence.",
}


def _build(skills: list[dict], comments: list[dict]) -> dict:
    model = {**MODEL_BASE, "skills": skills}
    return build_whub_json(
        SOURCE, "", comments, "Jean",
        hermes_runner=lambda prompt, timeout: (0, json.dumps(model, ensure_ascii=False), ""),
    )


def _items(data: dict) -> list[str]:
    return [item for skill in data["skills"] for item in skill["items"]]


def test_projects_fact_stops_at_the_formation_year_of_the_sidebar():
    facts = [entry for entry in extract_source_business_coverage_facts(SOURCE) if entry["section"] == "Projets"]

    assert facts == [
        {"section": "Projets", "fact": "plateforme Th@Bot"},
        {"section": "Projets", "fact": "API REST Node.js"},
    ]


def test_coverage_still_excludes_real_email_addresses():
    source = "Projets\n• Support projet: jean.martin@example.com\n• Refonte du portail de souscription\n"

    facts = [entry["fact"] for entry in extract_source_business_coverage_facts(source)]

    assert facts == ["Refonte du portail de souscription"]


def test_first_version_keeps_source_projects_without_formation_text():
    data = _build(MODEL_SKILLS_WITHOUT_PROJECTS, [])

    items = _items(data)
    assert "plateforme Th@Bot" in items
    assert "API REST Node.js" in items
    assert not any("Licence" in item or "Université" in item for item in items)
    assert REVISION_REMOVED_SOURCE_FACTS_KEY not in data


def test_skills_revision_comment_keeps_the_model_removal():
    data = _build(MODEL_SKILLS_WITHOUT_PROJECTS, [REMOVE_PROJECTS_COMMENT])

    assert [skill["category"] for skill in data["skills"]] == ["Méthodologies", "Cloud & DevOps"]
    assert "Projets" not in json.dumps(data["skills"], ensure_ascii=False)
    removed = [entry["fact"] for entry in data[REVISION_REMOVED_SOURCE_FACTS_KEY]]
    assert "plateforme Th@Bot" in removed and "API REST Node.js" in removed
    # The removal was asked for: it is not a fidelity warning.
    assert not any(
        warning["code"] == "source_coverage_missing_section" for warning in data.get("_fidelity_soft_warnings") or []
    )


def test_skills_revision_still_drops_items_absent_from_the_source():
    skills = [*MODEL_SKILLS_WITHOUT_PROJECTS, {"category": "Data & BI", "items": ["Databricks"]}]

    data = _build(skills, [REMOVE_PROJECTS_COMMENT])

    assert "Databricks" not in _items(data)


def test_skill_item_carrying_a_formation_is_a_fidelity_warning():
    leaked = [*MODEL_SKILLS_WITHOUT_PROJECTS, {"category": "Projets", "items": ["API REST Node.js 2014 Licence Informatique Université Paris Cité"]}]

    data = _build(leaked, [])

    codes = [warning["code"] for warning in data.get("_fidelity_soft_warnings") or []]
    assert "skill_item_contains_formation" in codes


def _pdf_text(lines: list[str], tmp_path) -> str:
    doc = fitz.open()
    page = doc.new_page()
    page.insert_text((40, 60), "\n".join(lines), fontsize=9)
    path = tmp_path / "out.pdf"
    doc.save(str(path))
    return "\n".join(p.get_text() for p in fitz.open(str(path)))


def test_pdf_qa_does_not_report_facts_removed_by_a_revision(tmp_path):
    text = _pdf_text(["Méthodologies", "Scrum", "Kanban"], tmp_path)
    structured = {
        "name": "JEAN",
        "experiences": [],
        REVISION_REMOVED_SOURCE_FACTS_KEY: [
            {"section": "Projets", "fact": "plateforme Th@Bot"},
            {"section": "Projets", "fact": "API REST Node.js"},
        ],
    }

    issues = find_pdf_source_fidelity_issues(text, source_text=SOURCE, structured_data=structured)
    missing = [issue["fact"] for issue in issues if issue["code"] == "source_coverage_missing_section"]

    assert "plateforme Th@Bot" not in missing
    assert "API REST Node.js" not in missing
    # Without the revision trail the same PDF is reported.
    issues = find_pdf_source_fidelity_issues(text, source_text=SOURCE, structured_data={"name": "JEAN", "experiences": []})
    assert "plateforme Th@Bot" in [issue["fact"] for issue in issues if issue["code"] == "source_coverage_missing_section"]
