"""Lot 2 (2026-11) : rangement de la section « Compétences techniques ».

Cas reconstitués à partir des défauts relevés sur 18 CV de production sur 20
(données anonymisées : personnes et missions inventées, seules des sociétés
génériques sont nommées).
"""
from __future__ import annotations

import importlib.util
import json
from copy import deepcopy
from pathlib import Path

import fitz
import pytest

from src.llm_backend import CV_JSON_SCHEMA, _normalize_structured_output
from src.qa import find_pdf_source_fidelity_issues
from src.skills_cleanup import (
    CLEANUP_REPORT_KEY,
    clean_skills_section,
    cleanup_qa_warning,
    repair_parentheses,
)
from src.structuring import (
    WHUB_SKILL_CATEGORY_TAXONOMY,
    _group_long_skills,
    _hermes_prompt,
    build_whub_json,
    extract_source_business_coverage_facts,
)

RENDERER_PATH = Path(__file__).resolve().parents[1] / "renderer" / "whub_cv_renderer.py"


def _items(data: dict) -> list[str]:
    return [item for skill in data["skills"] for item in skill["items"]]


def _categories(data: dict) -> list[str]:
    return [skill["category"] for skill in data["skills"]]


def _actions(data: dict) -> dict[str, list[str]]:
    out: dict[str, list[str]] = {}
    for entry in data[CLEANUP_REPORT_KEY]:
        out.setdefault(entry["action"], []).append(entry["item"])
    return out


# Source à deux colonnes (cas « d132b958 ») : la section Compétences n'a pas de
# titre de fin, les missions et l'EDUCATION suivent.
TWO_COLUMN_SOURCE = """Lucas TESTEUR
Business Analyst|Chef de projet
Compétences
Secteurs
Banque
Gestion de projet agile (Scrum)
Spécifications fonctionnelles
Assurance
Gestion de projet : Azure
Devops/Jira/Trello
Energie
Data Management : Excel,
SQL(SSMS), Power BI
Juin 2026-Dec 2026
Acme Services : Administration fonctionnelle de la facturation électronique (Esker, P2P)
• Gestion des droits utilisateurs
• Gestion des flux de facturation fournisseurs (Réception facture, TVA, échéance, paiement)
Juin 2022- Décembre 2022
Banque Exemple : Audit de faisabilité de création d'une base de données clients
• Cartographie des outils et données utilisés
EDUCATION
2017-2019 : Master Management Des Ressources Humaines/École de Commerce Exemple
Langues : Français (Maternel), anglais(professionnel)
Certifications : PSPO I, Lean Six Sigma (Green belt)
"""


def _polluted_two_column() -> dict:
    """Ce que l'ancien post-traitement livrait (réinjection + découpe sur virgules)."""
    return {
        "name": "LUCAS",
        "title": "Business Analyst",
        "formations": [{"date": "2017-2019", "degree": "Master Management Des Ressources Humaines", "school": "École de Commerce Exemple"}],
        "certifications": ["PSPO I", "Lean Six Sigma (Green belt)", "PSPO I, Lean Six Sigma (Green belt)"],
        "languages": [{"name": "Français", "level": "Maternel"}, {"name": "Anglais", "level": "professionnel"}],
        "skills": [
            {"category": "Méthodologies", "items": ["Agile (Scrum)", "Jira"]},
            {"category": "Autres", "items": [
                "Spécifications fonctionnelles", "Trello", "Excel", "Esker",
                "Gestion des flux de facturation fournisseurs (Réception facture", "TVA", "échéance", "paiement)",
                "Gestion des droits utilisateurs",
                "Paris Juin 2022- Décembre 2022 Banque Exemple : Audit de faisabilité de création d'une base de données clients",
            ]},
            {"category": "Autres (suite)", "items": ["Power BI", "Cartographie des outils et données utilisés"]},
            {"category": "Autres — suite 2", "items": ["EDUCATION 2017-2019 : Master Management Des Ressources Humaines/École de Commerce Exemple"]},
            {"category": "Secteurs d'activité", "items": ["Banque", "Assurance", "Energie"]},
            {"category": "Langues", "items": ["Français (Maternel)", "anglais(professionnel)"]},
            {"category": "Certifications", "items": ["PSPO I"]},
            {"category": "Soft skills", "items": ["Autonomie", "Rigueur"]},
        ],
        "experiences": [
            {"date": "Juin 2026-Dec 2026", "role": "Administration fonctionnelle de la facturation électronique (Esker, P2P)",
             "company_highlight": "Acme Services", "sections": [{"heading": "Missions clés", "content": [
                 "Gestion des droits utilisateurs",
                 "Gestion des flux de facturation fournisseurs (Réception facture, TVA, échéance, paiement)",
             ]}]},
            {"date": "Juin 2022- Décembre 2022", "role": "Business Analyst, Paris", "company_highlight": "Banque Exemple",
             "sections": [{"heading": "Missions clés", "content": ["Cartographie des outils et données utilisés"]}]},
        ],
    }


class TestCleanupOnPollutedSkills:
    def test_mission_text_education_languages_certifications_leave_the_skills(self):
        data = clean_skills_section(_polluted_two_column(), TWO_COLUMN_SOURCE)
        items = _items(data)
        text = " | ".join(items)

        for leaked in ("Juin 2022", "Banque Exemple", "Master", "EDUCATION", "Français", "PSPO", "Autonomie",
                       "Gestion des droits utilisateurs", "Cartographie des outils", "TVA", "échéance"):
            assert leaked not in text, leaked
        # Les vraies compétences restent.
        for skill in ("Agile (Scrum)", "Jira", "Spécifications fonctionnelles", "Trello", "Excel", "Esker", "Power BI", "Banque"):
            assert skill in items, skill

    def test_categories_are_merged_and_autres_appears_once(self):
        data = clean_skills_section(_polluted_two_column(), TWO_COLUMN_SOURCE)
        categories = _categories(data)

        assert not any("suite" in category.lower() for category in categories)
        assert sum(1 for category in categories if category.lower().startswith("autres")) <= 1
        assert len(categories) == len({category.lower() for category in categories})
        assert "Langues" not in categories and "Certifications" not in categories
        assert "Soft skills" not in categories

    def test_items_go_to_the_source_categories_when_the_source_groups_them(self):
        data = clean_skills_section(_polluted_two_column(), TWO_COLUMN_SOURCE)
        by_category = {skill["category"]: skill["items"] for skill in data["skills"]}

        assert "Trello" in by_category.get("Gestion de projet", [])
        assert "Excel" in by_category.get("Data Management", [])

    def test_mission_title_missing_from_the_experience_is_moved_into_it(self):
        data = clean_skills_section(_polluted_two_column(), TWO_COLUMN_SOURCE)
        bank = data["experiences"][1]

        assert bank["sections"][0] == {"heading": "Contexte", "content": ["Audit de faisabilité de création d'une base de données clients"]}
        assert "deplace_vers_experience" in _actions(data)

    def test_nothing_is_removed_silently(self):
        data = clean_skills_section(_polluted_two_column(), TWO_COLUMN_SOURCE)
        actions = _actions(data)

        assert any("Gestion des droits utilisateurs" in item for item in actions["texte_de_mission_supprime"])
        assert any("Master Management" in item for item in actions["formation_deja_presente"])
        assert actions["soft_skill_supprime"] == ["Autonomie", "Rigueur"]
        assert "langue_deja_presente" in actions and "certification_deja_presente" in actions
        warning = cleanup_qa_warning(data[CLEANUP_REPORT_KEY])
        assert warning["code"] == "skills_cleanup"
        assert any("Autonomie" in line for line in warning["details"])

    def test_duplicated_certification_and_languages_are_deduplicated(self):
        data = clean_skills_section(_polluted_two_column(), TWO_COLUMN_SOURCE)

        assert data["certifications"] == ["PSPO I", "Lean Six Sigma (Green belt)"]
        assert [language["name"] for language in data["languages"]] == ["Français", "Anglais"]

    def test_cleanup_is_idempotent(self):
        once = clean_skills_section(_polluted_two_column(), TWO_COLUMN_SOURCE)
        twice = clean_skills_section(once, TWO_COLUMN_SOURCE)

        assert twice["skills"] == once["skills"]
        assert twice["experiences"] == once["experiences"]
        assert twice["certifications"] == once["certifications"]


class TestCleanupDetails:
    @pytest.mark.parametrize("raw, repaired", [
        ("React (TypeScript", "React (TypeScript)"),
        ("(MCP", "MCP"),
        ("Redux)", "Redux"),
        ("Jira (avancé", "Jira (avancé)"),
        ("Méthodologies agiles (certifiée PSPO)", "Méthodologies agiles (certifiée PSPO)"),
        ("()", ""),
    ])
    def test_unclosed_parentheses_are_repaired(self, raw, repaired):
        assert repair_parentheses(raw) == repaired

    def test_comma_split_fragments_are_glued_back(self):
        data = {"skills": [{"category": "Frontend", "items": ["React (TypeScript", "Redux)", "Vue.js"]}], "experiences": []}

        cleaned = clean_skills_section(data)

        assert _items(cleaned) == ["React (TypeScript, Redux)", "Vue.js"]

    def test_duplicates_ignore_case_accents_and_punctuation(self):
        data = {"skills": [
            {"category": "Méthodologies", "items": ["Agile", "agile", "Gestion de projet agile (Scrum)"]},
            {"category": "Cloud & DevOps", "items": ["Azure DevOps", "AZURE devops", "Intégration continue"]},
            {"category": "Outils", "items": ["Integration continue", "PostgreSQL", "Postgresql"]},
        ], "experiences": []}

        cleaned = clean_skills_section(data)

        assert _items(cleaned) == ["Agile", "Gestion de projet agile (Scrum)", "Azure DevOps", "Intégration continue", "PostgreSQL"]
        assert len(_actions(cleaned)["doublon_supprime"]) == 4

    def test_versions_with_years_are_not_mission_dates(self):
        data = {"skills": [{"category": "Systèmes", "items": ["Windows Server 2000-2022", "SCOM 2007/2012", "Office 2016"]}], "experiences": []}

        cleaned = clean_skills_section(data)

        assert _items(cleaned) == ["Windows Server 2000-2022", "SCOM 2007/2012", "Office 2016"]

    def test_master_data_and_scrum_master_are_skills_not_degrees(self):
        data = {"skills": [{"category": "Méthodologies", "items": ["Scrum Master", "Master Data Management"]}], "experiences": []}

        assert _items(clean_skills_section(data)) == ["Scrum Master", "Master Data Management"]

    def test_uncovered_project_phrases_move_to_projects(self):
        data = {"skills": [
            {"category": "Backend", "items": ["Java"]},
            {"category": "Projets", "items": ["Refonte du portail de souscription en ligne pour un assureur", "Kotlin"]},
        ], "experiences": []}

        cleaned = clean_skills_section(data)

        assert cleaned["projects"] == [{"name": "", "date": "", "details": ["Refonte du portail de souscription en ligne pour un assureur"]}]
        assert "Projets" not in _categories(cleaned)
        assert "Kotlin" in _items(cleaned)

    def test_language_moved_when_missing_from_languages(self):
        data = {"skills": [{"category": "Langues", "items": ["Espagnol (B2)"]}], "languages": [], "experiences": []}

        cleaned = clean_skills_section(data)

        assert cleaned["languages"] == [{"name": "Espagnol", "level": "B2"}]
        assert cleaned["skills"] == []

    def test_certification_moved_when_missing_from_certifications(self):
        data = {"skills": [{"category": "Cloud & DevOps", "items": ["Azure", "AZ-900 Microsoft Azure Fundamentals"]}],
                "certifications": [], "experiences": []}

        cleaned = clean_skills_section(data)

        assert cleaned["certifications"] == ["AZ-900 Microsoft Azure Fundamentals"]
        assert _items(cleaned) == ["Azure"]

    def test_languages_glued_with_the_source_page_header_are_split(self):
        # Cas « 48779cc0 » : trois langues et le pied de page du CV source dans un seul niveau.
        data = {"name": "LINA", "skills": [], "experiences": [], "languages": [{
            "name": "Français",
            "level": "langue maternelle Arabe: langue maternelle Anglais: professionnel Lina · Ingénieur QA Page 4 / 4",
        }]}

        cleaned = clean_skills_section(data)

        assert cleaned["languages"] == [
            {"name": "Français", "level": "langue maternelle"},
            {"name": "Arabe", "level": "langue maternelle"},
            {"name": "Anglais", "level": "professionnel"},
        ]
        assert "langue_redecoupee" in _actions(cleaned)

    def test_soft_skills_kept_when_a_skills_revision_asked_for_them(self):
        data = {"skills": [{"category": "Compétences clés", "items": ["Leadership", "Java"]}], "experiences": []}

        assert _items(clean_skills_section(data, keep_soft_skills=True)) == ["Leadership", "Java"]
        assert _items(clean_skills_section(data)) == ["Java"]

    def test_too_many_small_categories_are_regrouped(self):
        data = {"skills": [{"category": f"Domaine {index}", "items": [f"Outil{index}"]} for index in range(12)], "experiences": []}

        cleaned = clean_skills_section(data)

        assert len(cleaned["skills"]) <= 8
        assert sorted(_items(cleaned)) == sorted(f"Outil{index}" for index in range(12))


class TestCorrectModelOutputIsLeftAlone:
    CLEAN = {
        "name": "INES",
        "title": "Développeuse Full Stack",
        "formations": [{"date": "2019", "degree": "Master Informatique", "school": "Université Exemple"}],
        "certifications": ["AWS Certified Cloud Practitioner"],
        "languages": [{"name": "Anglais", "level": "courant"}],
        "skills": [
            {"category": "Backend", "items": ["Java", "Spring Boot", "API REST"]},
            {"category": "Frontend", "items": ["React (TypeScript, Redux)", "Angular"]},
            {"category": "Cloud & DevOps", "items": ["AWS", "Docker", "Kubernetes", "GitLab CI/CD"]},
            {"category": "Méthodologies", "items": ["Scrum", "Kanban"]},
        ],
        "experiences": [{"date": "2021 - 2024", "role": "Développeuse", "company_highlight": "Acme", "sections": [
            {"heading": "Missions clés", "content": ["Développement des API REST en Java et Spring Boot"]}]}],
    }

    def test_clean_json_goes_through_unchanged(self):
        cleaned = clean_skills_section(deepcopy(self.CLEAN), "Compétences\nJava, Spring Boot\n")

        for key in ("skills", "experiences", "formations", "certifications", "languages"):
            assert cleaned[key] == self.CLEAN[key], key
        assert "projects" not in cleaned
        assert cleanup_qa_warning(cleaned[CLEANUP_REPORT_KEY]) is None

    def test_group_long_skills_keeps_parentheses_and_creates_no_autres(self):
        grouped = _group_long_skills([{"category": "Compétences techniques", "items": [
            "Java", "Spring", "React (TypeScript, Redux)", "AWS", "Docker", "Kubernetes", "PostgreSQL",
            "Jira", "Confluence", "Figma", "Excel", "Notion", "Miro", "Postman",
        ]}])

        assert "React (TypeScript, Redux)" in _items({"skills": grouped})
        assert not any(skill["category"].startswith("Autres") or "suite" in skill["category"] for skill in grouped)


SOURCE_WITH_PROJECTS = """Ines
Développeuse Full Stack
Compétences
Java
Spring Boot
React
PROJETS
• Refonte du portail de souscription en ligne
• Migration ERP vers le cloud
ÉDUCATION
2016
Master Management des SI
Université Exemple
EXPÉRIENCES
2021 - 2024 Développeuse Acme
• Développement des API REST en Java
"""


def _model(**overrides) -> dict:
    model = {
        "name": "INES",
        "title": "Développeuse Full Stack",
        "description": "",
        "formations": [{"date": "2016", "degree": "Master Management des SI", "school": "Université Exemple"}],
        "certifications": [],
        "languages": [],
        "skills": [{"category": "Backend", "items": ["Java", "Spring Boot"]}, {"category": "Frontend", "items": ["React"]}],
        "experiences": [{"date": "2021 - 2024", "role": "Développeuse", "company_highlight": "Acme",
                         "sections": [{"heading": "Missions clés", "content": ["Développement des API REST en Java"]}]}],
        "projects": [],
    }
    model.update(overrides)
    return model


def _run(model: dict, source: str = SOURCE_WITH_PROJECTS) -> dict:
    return build_whub_json(source, "", [], "Ines",
                           hermes_runner=lambda prompt, timeout: (0, json.dumps(model, ensure_ascii=False), ""))


class TestPipeline:
    def test_education_heading_closes_the_projects_section(self):
        facts = extract_source_business_coverage_facts(SOURCE_WITH_PROJECTS)

        assert [entry["fact"] for entry in facts if entry["section"] == "PROJETS" or entry["section"].lower() == "projets"] == [
            "Refonte du portail de souscription en ligne",
            "Migration ERP vers le cloud",
        ]

    def test_correct_model_json_is_not_broken_by_the_post_processing(self):
        model = _model(projects=[{"name": "Refonte du portail de souscription en ligne", "date": "", "details": []},
                                 {"name": "Migration ERP vers le cloud", "date": "", "details": []}])

        data = _run(model)

        assert data["skills"] == model["skills"]
        # Empty strings/lists are dropped by the contact sanitizer; the content is the same.
        assert [project["name"] for project in data["projects"]] == [project["name"] for project in model["projects"]]
        assert not any(project.get("details") for project in data["projects"])
        assert data["formations"] == model["formations"]
        assert data["experiences"] == model["experiences"]
        assert cleanup_qa_warning(data.get(CLEANUP_REPORT_KEY)) is None

    def test_projects_left_out_by_the_model_go_to_projects_not_skills(self):
        data = _run(_model())

        details = [detail for project in data["projects"] for detail in project["details"]]
        assert details == ["Refonte du portail de souscription en ligne", "Migration ERP vers le cloud"]
        assert "Projets" not in _categories(data)
        assert not any("Master" in text or "ÉDUCATION" in text for text in details + _items(data))
        assert not any(skill["category"] == "Méthodologies" and "Gestion de projet : Agile" in skill["items"] for skill in data["skills"])

    def test_model_dumping_missions_into_skills_is_cleaned(self):
        polluted = _model(skills=[
            {"category": "Backend", "items": ["Java", "Spring Boot"]},
            {"category": "Autres", "items": ["2021 - 2024 Développeuse Acme", "Développement des API REST en Java", "React"]},
            {"category": "Autres (suite)", "items": ["Master Management des SI Université Exemple"]},
        ])

        data = _run(polluted)

        assert _items(data) == ["Java", "Spring Boot", "React"]
        assert data[CLEANUP_REPORT_KEY]


class TestPrompt:
    PROMPT = _hermes_prompt("CV source", "", [], "Ines")

    def test_no_reference_to_an_unloaded_skill(self):
        assert "whub-client-cv-generator" not in self.PROMPT
        assert "déjà chargé" not in self.PROMPT

    @pytest.mark.parametrize("rule", [
        "Compétence technique (",
        "Outil (",
        "Méthodologie (",
        "Soft skill / savoir-être",
        "Langue parlée: uniquement `languages`",
        "Certification (titre délivré par un organisme",
        "Formation / diplôme (",
        "Stage: c'est une expérience professionnelle",
        "Contexte de mission (",
        "Réalisation ou projet mené dans une mission",
        "Projet ou réalisation hors expérience",
    ])
    def test_one_rule_per_type_of_information(self, rule):
        assert self.PROMPT.count(rule) == 1

    def test_no_contradiction_on_categories(self):
        assert "Taxonomie fermée" not in self.PROMPT
        assert "N'utilise jamais `Autres`" not in self.PROMPT
        assert "pas de `(suite)`" in self.PROMPT
        assert "Ne supprime pas une compétence technique réelle pour tenir ces limites" in self.PROMPT

    def test_taxonomy_has_no_languages_nor_certifications(self):
        assert "Langues" not in WHUB_SKILL_CATEGORY_TAXONOMY
        assert "Certifications" not in WHUB_SKILL_CATEGORY_TAXONOMY

    def test_prompt_schema_matches_the_llm_schema(self):
        for key in CV_JSON_SCHEMA["required"]:
            assert f'"{key}"' in self.PROMPT, key
        project = CV_JSON_SCHEMA["properties"]["projects"]["items"]
        assert project["required"] == ["name", "date", "details"]
        assert project["additionalProperties"] is False

    def test_empty_projects_are_dropped_from_the_model_output(self):
        raw = json.dumps({"name": "X", "projects": [{"name": "", "date": "", "details": []}]})
        assert "projects" not in json.loads(_normalize_structured_output(raw))


class TestRenderingAndQa:
    def test_projects_block_is_rendered_and_checked_by_qa(self, tmp_path):
        spec = importlib.util.spec_from_file_location("whub_cv_renderer_projects", RENDERER_PATH)
        renderer = importlib.util.module_from_spec(spec)
        assert spec.loader
        spec.loader.exec_module(renderer)
        renderer.prep_assets()
        renderer.register_fonts(renderer.ensure_poppins())
        data = _model(projects=[{"name": "Refonte du portail de souscription", "date": "2023", "details": ["Migration ERP vers le cloud"]},
                                {"name": "", "date": "", "details": ["Outil interne de suivi des tickets"]}])
        out = tmp_path / "cv.pdf"
        renderer.render_document(str(out), data)

        text = "\n".join(page.get_text() for page in fitz.open(str(out)))
        assert "P R O J E T S" in text
        for fact in ("Refonte du portail de souscription", "Migration ERP vers le cloud", "Outil interne de suivi des tickets"):
            assert fact in text
        issues = find_pdf_source_fidelity_issues(text, structured_data=data)
        assert not [issue for issue in issues if issue["code"] == "json_fact_missing_from_pdf"]

    def test_no_empty_skills_title_when_nothing_is_left(self, tmp_path):
        spec = importlib.util.spec_from_file_location("whub_cv_renderer_empty", RENDERER_PATH)
        renderer = importlib.util.module_from_spec(spec)
        assert spec.loader
        spec.loader.exec_module(renderer)
        renderer.prep_assets()
        renderer.register_fonts(renderer.ensure_poppins())
        out = tmp_path / "cv.pdf"
        renderer.render_document(str(out), _model(skills=[]))

        text = fitz.open(str(out))[0].get_text()
        assert "C O M P É T E N C E S" not in text
        assert "X P É R I E N C E S" in text

    def test_qa_counts_logged_removals_as_accounted_for(self):
        source = "Compétences\nJava\nAutonomie\nEXPÉRIENCES\n"
        removed = {CLEANUP_REPORT_KEY: [{"action": "soft_skill_supprime", "item": "Autonomie", "category": "Compétences"}]}

        issues = find_pdf_source_fidelity_issues("Java", source_text=source, structured_data=removed)
        assert not [issue for issue in issues if issue["code"] == "source_coverage_missing_section"]
        issues = find_pdf_source_fidelity_issues("Java", source_text=source, structured_data={})
        assert [issue for issue in issues if issue["code"] == "source_coverage_missing_section"]
