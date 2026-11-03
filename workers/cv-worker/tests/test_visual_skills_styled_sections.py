"""Style-aware skills extraction (Canva-style two-column templates).

Layout read from the PDF styles: a large section heading ("C O M P É T E N C E S
T E C H N I Q U E S"), bold category lines, "•" bullet items whose wrapped
lines continue below, and a sidebar column (formations) that must not leak in.
"""
from pathlib import Path

import fitz
import pytest

from src.visual_skills_extraction import extract_visual_skills

LEFT, MIDDLE, RIGHT = 60, 234, 432


def _pdf(tmp_path: Path, lines: list[tuple[float, float, str, str, float]]) -> Path:
    """lines: (x, y, text, font, size) with font "bold" or "regular"."""
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    for x, y, text, font, size in lines:
        page.insert_text((x, y), text, fontname="hebo" if font == "bold" else "helv", fontsize=size)
    path = tmp_path / "cv.pdf"
    doc.save(str(path))
    return path


def _heading(x, y, text):
    return (x, y, " ".join(text), "bold", 14)


def _cat(x, y, text):
    return (x, y, text, "bold", 8.4)


def _line(x, y, text):
    return (x, y, text, "regular", 8)


def _body_padding(y):
    # Body text so the median font size is the item size, as in real CVs.
    return [_line(LEFT, y + i * 10, f"Ligne de description du profil numéro {i}.") for i in range(6)]


def _by_category(result):
    return {skill["category"]: skill["items"] for skill in result.skills}


def _two_column_skills_pdf(tmp_path):
    return _pdf(tmp_path, [
        _heading(LEFT, 60, "DESCRIPTION"),
        *_body_padding(80),
        _heading(RIGHT, 150, "FORMATIONS"),
        _heading(LEFT, 150, "COMPÉTENCES"),
        _cat(LEFT, 180, "Pilotage de Projets"),
        _line(LEFT, 190, "• Méthodologies agiles (certifiée PSPO),"),
        _line(LEFT, 200, "Cycle V, hybride"),
        _line(LEFT, 210, "• Planning prévisionnel, plan de charge,"),
        _line(LEFT, 220, "budget"),
        _cat(MIDDLE, 180, "Relation Client"),
        _line(MIDDLE, 190, "• CRM (PEGA, Salesforce) : audit,"),
        _line(MIDDLE, 200, "migration des données"),
        _line(MIDDLE, 210, "• Maquettes et wireframes, UX/UI"),
        _cat(LEFT, 240, "Data & Décisionnel"),
        _line(LEFT, 250, "• Cartographie des usages de données"),
        _cat(MIDDLE, 240, "Compétences techniques"),
        _line(MIDDLE, 250, "• Environnements Microsoft 365, Azure"),
        _line(MIDDLE, 260, "EntraID"),
        (RIGHT, 180, "2001", "bold", 8.8),
        (RIGHT, 190, "HND Business Studies", "bold", 8.8),
        (RIGHT, 200, "London Metropolitan University", "regular", 8.8),
        _heading(LEFT, 300, "EXPÉRIENCES"),
        _line(LEFT, 320, "• Pilotage du programme de migration cloud AWS."),
    ])


def test_two_column_categories_are_read_in_source_order_with_whole_bullets(tmp_path):
    result = extract_visual_skills(_two_column_skills_pdf(tmp_path))

    assert result.confidence >= 0.75, result.warnings
    assert result.skills == [
        {"category": "Pilotage de Projets", "items": [
            "Méthodologies agiles (certifiée PSPO), Cycle V, hybride",
            "Planning prévisionnel, plan de charge, budget",
        ]},
        {"category": "Relation Client", "items": [
            "CRM (PEGA, Salesforce) : audit, migration des données",
            "Maquettes et wireframes, UX/UI",
        ]},
        {"category": "Data & Décisionnel", "items": ["Cartographie des usages de données"]},
        {"category": "Compétences techniques", "items": ["Environnements Microsoft 365, Azure EntraID"]},
    ]


def test_non_skill_categories_are_left_out_and_continued_ones_merged(tmp_path):
    result = extract_visual_skills(_pdf(tmp_path, [
        *_body_padding(60),
        _heading(LEFT, 150, "COMPÉTENCES TECHNIQUES"),
        _cat(LEFT, 180, "DevOps / CI/CD"),
        _line(LEFT, 190, "• Terraform"),
        _line(LEFT, 200, "• Ansible"),
        _cat(MIDDLE, 180, "Langages"),
        _line(MIDDLE, 190, "• Python"),
        _line(MIDDLE, 200, "• Go"),
        _cat(LEFT, 220, "Loisirs et Centres d'Intérêt"),
        _line(LEFT, 230, "• Cuisine"),
        _cat(MIDDLE, 220, "Compétences Linguistiques"),
        _line(MIDDLE, 230, "• Anglais : courant"),
        _cat(LEFT, 250, "DevOps / CI/CD (suite)"),
        _line(LEFT, 260, "• GitLab"),
        _line(LEFT, 270, "• Harbor"),
        _heading(LEFT, 300, "EXPÉRIENCES"),
    ]))

    assert result.confidence >= 0.75, result.warnings
    assert _by_category(result) == {
        "DevOps / CI/CD": ["Terraform", "Ansible", "GitLab", "Harbor"],
        "Langages": ["Python", "Go"],
    }


def test_category_heading_wrapped_on_two_bold_lines_is_one_category(tmp_path):
    result = extract_visual_skills(_pdf(tmp_path, [
        *_body_padding(60),
        _heading(LEFT, 150, "COMPÉTENCES"),
        _cat(LEFT, 180, "Compétences et"),
        _cat(LEFT, 190, "outils"),
        _line(LEFT, 200, "• Management d'équipe"),
        _line(LEFT, 210, "• MS Project"),
        _line(LEFT, 220, "• Visio"),
        _cat(MIDDLE, 180, "Processus métiers"),
        _line(MIDDLE, 190, "• Supply chain"),
        _line(MIDDLE, 200, "• Gestion de projets informatiques"),
        _line(MIDDLE, 210, "• Achats"),
        _heading(LEFT, 300, "EXPÉRIENCES"),
    ]))

    assert _by_category(result) == {
        "Compétences et outils": ["Management d'équipe", "MS Project", "Visio"],
        "Processus métiers": ["Supply chain", "Gestion de projets informatiques", "Achats"],
    }


def test_unbulleted_comma_list_is_split_into_atomic_items(tmp_path):
    result = extract_visual_skills(_pdf(tmp_path, [
        *_body_padding(60),
        _heading(LEFT, 150, "COMPÉTENCES"),
        _cat(LEFT, 180, "Stack technique"),
        _line(LEFT, 190, "Python, Java, TypeScript (React, Next.js),"),
        _line(LEFT, 200, "PostgreSQL, Docker"),
        _cat(LEFT, 220, "Méthodes"),
        _line(LEFT, 230, "Agile Scrum, Kanban, TDD"),
        _heading(LEFT, 300, "EXPÉRIENCES"),
    ]))

    assert result.confidence >= 0.75, result.warnings
    assert _by_category(result) == {
        "Stack technique": ["Python", "Java", "TypeScript (React, Next.js)", "PostgreSQL", "Docker"],
        "Méthodes": ["Agile Scrum", "Kanban", "TDD"],
    }


def test_broken_sentence_fragments_are_not_trusted(tmp_path):
    # Sanitizer fixture: bullets cut mid-sentence ("• risques. Data & Cloud: AWS").
    result = extract_visual_skills(_pdf(tmp_path, [
        *_body_padding(60),
        _heading(LEFT, 150, "COMPÉTENCES"),
        _cat(LEFT, 180, "Compétences"),
        _line(LEFT, 190, "• risques. Data & Cloud: AWS"),
        _line(LEFT, 200, "• SQL. DevOps: GitHub Actions"),
        _line(LEFT, 210, "• Gestion de projet: Scrum"),
        _cat(MIDDLE, 180, "Projets"),
        _line(MIDDLE, 190, "• plateforme Th@Bot"),
        _line(MIDDLE, 200, "• API REST Node.js"),
        _heading(LEFT, 300, "EXPÉRIENCES"),
    ]))

    assert result.confidence < 0.75


BANK = Path(__file__).resolve().parents[3] / "cv_test_bank"


@pytest.mark.skipif(not (BANK / "Zahia_location_and_role_facts" / "input.pdf").exists(), reason="test bank absent")
def test_zahia_skills_match_the_source_layout():
    result = extract_visual_skills(BANK / "Zahia_location_and_role_facts" / "input.pdf")
    by_category = _by_category(result)

    assert result.confidence >= 0.75
    assert list(by_category) == ["Pilotage de Projets", "Relation Client & parcours digitaux", "Data & Décisionnel", "Compétences techniques"]
    assert "CRM (PEGA, Salesforce) : audit, migration des données, plan de décommissionnement" in by_category["Relation Client & parcours digitaux"]
    assert by_category["Compétences techniques"][-1] == "Environnements Microsoft 365, Azure EntraID"
    assert not any("University" in item or "ZAHIA" in item for items in by_category.values() for item in items)


@pytest.mark.skipif(not (BANK / "Hodard_continuity" / "input.pdf").exists(), reason="test bank absent")
def test_hodard_continued_category_is_merged():
    by_category = _by_category(extract_visual_skills(BANK / "Hodard_continuity" / "input.pdf"))

    assert "DevOps / CI/CD (suite)" not in by_category
    assert by_category["DevOps / CI/CD"][-2:] == ["GitLab", "Harbor"]
    assert "Centres d'intérêt" not in by_category


def test_bulleted_tool_list_is_split_but_bulleted_phrase_is_kept(tmp_path):
    result = extract_visual_skills(_pdf(tmp_path, [
        *_body_padding(60),
        _heading(LEFT, 150, "COMPÉTENCES"),
        _cat(LEFT, 180, "Stack"),
        _line(LEFT, 190, "• Python, Java, Next.js, Azure DevOps"),
        _line(LEFT, 200, "• Agile Scrum, Code review, TDD"),
        _line(LEFT, 210, "• Django, PyTest"),
        _cat(MIDDLE, 180, "Pilotage"),
        _line(MIDDLE, 190, "• Planning prévisionnel, plan de charge, budget"),
        _line(MIDDLE, 200, "• Maquettes et wireframes, UX/UI"),
        _line(MIDDLE, 210, "• Tests API : Postman, SoapUI"),
        _heading(LEFT, 300, "EXPÉRIENCES"),
    ]))

    assert _by_category(result) == {
        "Stack": ["Python", "Java", "Next.js", "Azure DevOps", "Agile Scrum", "Code review", "TDD", "Django", "PyTest"],
        "Pilotage": ["Planning prévisionnel, plan de charge, budget", "Maquettes et wireframes, UX/UI", "Tests API : Postman, SoapUI"],
    }


def _skills_lines_without_closing_heading():
    return [
        *_body_padding(60),
        _heading(LEFT, 150, "COMPÉTENCES"),
        _cat(LEFT, 180, "Langages"),
        *[_line(LEFT, 190 + i * 10, f"• Outil {i}") for i in range(4)],
        _cat(MIDDLE, 180, "Cloud"),
        *[_line(MIDDLE, 190 + i * 10, f"• Service {i}") for i in range(4)],
    ]


def test_section_not_closed_on_its_page_is_not_trusted(tmp_path):
    # The skills may go on next page: replacing the model skills would lose them.
    result = extract_visual_skills(_pdf(tmp_path, _skills_lines_without_closing_heading()))

    assert result.confidence < 0.75
    assert "skills_section_may_continue" in result.warnings


def test_closed_section_is_trusted(tmp_path):
    result = extract_visual_skills(_pdf(tmp_path, [*_skills_lines_without_closing_heading(), _heading(LEFT, 300, "EXPÉRIENCES")]))

    assert result.confidence >= 0.75, result.warnings


def test_lines_before_the_first_category_are_not_dropped_silently(tmp_path):
    result = extract_visual_skills(_pdf(tmp_path, [
        *_body_padding(60),
        _heading(LEFT, 150, "COMPÉTENCES"),
        _line(LEFT, 165, "• Gestion de projet"),
        *_skills_lines_without_closing_heading()[7:],
        _heading(LEFT, 300, "EXPÉRIENCES"),
    ]))

    assert result.confidence < 0.75
    assert "uncategorised_skill_lines" in result.warnings


def test_section_ending_with_its_page_is_closed_by_next_page_heading(tmp_path):
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    for x, y, text, font, size in _skills_lines_without_closing_heading():
        page.insert_text((x, y), text, fontname="hebo" if font == "bold" else "helv", fontsize=size)
    next_page = doc.new_page(width=595, height=842)
    next_page.insert_text((LEFT, 35), "JEAN", fontname="hebo", fontsize=8.3)
    next_page.insert_text((LEFT, 68), " ".join("EXPÉRIENCES"), fontname="hebo", fontsize=13.6)
    next_page.insert_text((LEFT, 100), "• Pilotage du programme de migration cloud AWS.", fontname="helv", fontsize=8)
    path = tmp_path / "two_pages.pdf"
    doc.save(str(path))

    assert extract_visual_skills(path).confidence >= 0.75
