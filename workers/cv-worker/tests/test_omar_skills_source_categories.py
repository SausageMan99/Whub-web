from pathlib import Path

from src.visual_skills_extraction import extract_visual_skills

ROOT = Path(__file__).resolve().parents[3]
OMAR_PDF = ROOT / "cv_test_bank" / "Omar_skills_source_categories" / "input.pdf"


def _skills_by_category():
    result = extract_visual_skills(OMAR_PDF)
    return result, {skill["category"]: skill["items"] for skill in result.skills}


def test_omar_source_skill_categories_are_preserved():
    result, by_category = _skills_by_category()

    assert result.confidence >= 0.75
    assert "Technologies Plateformes" in by_category
    assert "Front-end" in by_category
    assert "Data" in by_category
    assert "Ops" in by_category
    assert "Méthodologies" in by_category
    assert "Réseau & Sécurité" in by_category
    assert "Qualité & Analyse" in by_category
    assert "Messaging" in by_category
    assert "Divers" in by_category
    assert "Autres" not in by_category


def test_omar_ops_items_are_atomic_and_in_source_order():
    _, by_category = _skills_by_category()

    assert by_category["Ops"] == [
        "Git",
        "GitHub",
        "TeamCity",
        "Azure",
        "MsBuild",
        "PowerShell",
        "SVN",
        "TFS",
        "Kubernetes",
    ]


def test_omar_parenthetical_platform_items_are_preserved():
    _, by_category = _skills_by_category()

    assert ".NET (C#, WPF, WinForms, LINQ)" in by_category["Technologies Plateformes"]
    assert "ASP.NET (MVC, Web API, Razor, Blazor)" in by_category["Technologies Plateformes"]


def test_omar_source_skills_do_not_include_certification_blob_or_footer():
    result, by_category = _skills_by_category()
    all_items = [item for items in by_category.values() for item in items]

    assert not any("CV créé sur" in item for item in all_items)
    assert not any("Microsoft Certified Professional Developer" in item for item in all_items)
    assert all(len(item) <= 120 for item in all_items)
    assert result.warnings == []
