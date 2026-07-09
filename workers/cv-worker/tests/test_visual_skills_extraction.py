from pathlib import Path

import pytest

from src.visual_skills_extraction import (
    VisualSkillsResult,
    _is_footer_text,
    _is_skill_section_heading,
    apply_visual_skills_override,
    extract_visual_skills,
)


ROOT = Path(__file__).resolve().parents[3]
EZZOUBIR_PDF = ROOT / "cv_test_bank" / "Ezzoubir_skills_section_preservation" / "input.pdf"


def _category(result, name: str) -> list[str]:
    for skill in result.skills:
        if skill.get("category") == name:
            return skill.get("items") or []
    raise AssertionError(f"missing category {name!r}; got {[s.get('category') for s in result.skills]}")


def test_is_footer_text_detects_hellowork_footers():
    assert _is_footer_text("CV créé sur")
    assert _is_footer_text("3 / 6")
    assert _is_footer_text("4 / 6 CV créé sur")
    assert not _is_footer_text("COBOL")
    assert not _is_footer_text("Base De Données")


@pytest.mark.parametrize("text", [
    "Compétences fonctionnelles",
    "Méthodologie de travail",
    "Mainframe",
    "Web .NET",
    "Testeur fonctionnel",
    "Base De Données",
    "Compétences Organisationnelles",
    "Java",
])
def test_is_skill_section_heading_accepts_ezzoubir_headings(text):
    assert _is_skill_section_heading(text)


@pytest.mark.parametrize("text", [
    "Maintenance applicative et évolutive sur le référentiel des personnes morales.",
    "Analyse et rédaction des documents fonctionnelles et techniques",
    "Livraisons des programmes, les JCL et les plans DB2 sur tous les environnements de travail",
])
def test_is_skill_section_heading_rejects_experience_sentences(text):
    assert not _is_skill_section_heading(text)


def test_extract_visual_skills_preserves_ezzoubir_source_sections():
    result = extract_visual_skills(EZZOUBIR_PDF)

    assert result.confidence >= 0.75
    assert [skill["category"] for skill in result.skills] == [
        "Compétences fonctionnelles",
        "Méthodologie de travail",
        "Mainframe",
        "Web .NET",
        "Testeur fonctionnel",
        "Base De Données",
        "Compétences Organisationnelles",
        "Java",
    ]

    assert "Le lexique de la banque" in _category(result, "Compétences fonctionnelles")
    assert "Agile Scrum" in _category(result, "Méthodologie de travail")
    assert "COBOL" in _category(result, "Mainframe")
    assert "IMSBATCH" in _category(result, "Mainframe")
    assert "C#" in _category(result, "Web .NET")
    assert ".NET" in _category(result, "Web .NET")
    assert "Testeur" in _category(result, "Testeur fonctionnel")
    assert "Oracle" in _category(result, "Base De Données")
    assert "Planification" in _category(result, "Compétences Organisationnelles")
    assert "Java Spring" in _category(result, "Java")


def test_extract_visual_skills_excludes_footers_and_experience_sentences():
    result = extract_visual_skills(EZZOUBIR_PDF)
    flat = "\n".join(
        item
        for skill in result.skills
        for item in skill.get("items", [])
    )

    assert "CV créé sur" not in flat
    assert "3 / 6" not in flat
    assert "4 / 6" not in flat
    assert "Maintenance applicative et évolutive sur le référentiel" not in flat
    assert "Analyse et rédaction des documents" not in flat
    assert all(len(item) <= 120 for skill in result.skills for item in skill.get("items", []))


def test_apply_visual_skills_override_replaces_skills_when_confident():
    structured = {"name": "CV", "skills": [{"category": "Backend", "items": ["bad"]}]}
    visual = VisualSkillsResult(
        skills=[{"category": "Mainframe", "items": ["COBOL"]}],
        confidence=0.9,
        warnings=[],
    )

    result = apply_visual_skills_override(structured, visual, min_confidence=0.75)

    assert result["skills"] == [{"category": "Mainframe", "items": ["COBOL"]}]
    assert result["_source_overrides"]["skills"]["source"] == "visual_pdf_blocks"
    assert result["_source_overrides"]["skills"]["confidence"] == 0.9


def test_apply_visual_skills_override_keeps_existing_skills_when_low_confidence():
    structured = {"name": "CV", "skills": [{"category": "Backend", "items": ["Java"]}]}
    visual = VisualSkillsResult(skills=[], confidence=0.4, warnings=["too_few_visual_skills"])

    result = apply_visual_skills_override(structured, visual, min_confidence=0.75)

    assert result["skills"] == [{"category": "Backend", "items": ["Java"]}]
    assert "_source_overrides" not in result


def test_extract_visual_skills_returns_low_confidence_for_unreadable_pdf(tmp_path: Path):
    pdf_path = tmp_path / "invalid.pdf"
    pdf_path.write_bytes(b"%PDF fake")

    result = extract_visual_skills(pdf_path)

    assert result.skills == []
    assert result.confidence == 0.0
    assert "pdf_unreadable" in result.warnings
