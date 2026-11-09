import copy
import json
from pathlib import Path

from src.layout_packing import (
    assert_packing_preserves_experience_content,
    build_layout_packing_options,
    compute_experience_page_breaks,
)


def _exp(label: str, bullets: int) -> dict:
    return {
        "date": "2024",
        "role": label,
        "company_highlight": label,
        "sections": [{"heading": "Missions clés", "content": [f"Bullet {label} {i} avec un texte source fidèle." for i in range(bullets)]}],
    }


def test_packing_groups_oussama_like_experience_sizes_without_company_hardcode():
    experiences = [
        _exp("A", 4),
        _exp("B", 4),
        _exp("C", 2),
        _exp("D", 2),
        _exp("E", 2),
        _exp("F", 1),
        _exp("G", 1),
        _exp("H", 1),
    ]

    assert compute_experience_page_breaks(experiences, page_capacity_units=18) == [2, 5]


def test_real_oussama_fixture_groups_middle_and_final_experiences_as_planned():
    fixture = Path(__file__).parent / "fixtures" / "oussama_structured_faithful.json"
    data = json.loads(fixture.read_text(encoding="utf-8"))

    options = build_layout_packing_options(data)

    assert options["force_page_break_before_experience_indexes"] == []
    assert options["force_experiences_new_page"] is False


def test_layout_packing_options_are_non_destructive_and_expose_force_breaks():
    # Explicit request only. A page now counts 58 units (~ one rendered line
    # each) instead of 21, so the breaks fall about one full page apart.
    data = {"name": "O", "title": "T", "formations": [], "skills": [], "experiences": [_exp(label, 20) for label in "ABCDE"]}
    original = copy.deepcopy(data)

    options = build_layout_packing_options(data, force_experiences_new_page=True)
    payload = copy.deepcopy(data)
    payload["_layout"] = options

    assert data == original
    assert options["force_experiences_new_page"] is True
    assert options["force_page_break_before_experience_indexes"] == [2, 4]
    assert_packing_preserves_experience_content(data, payload)


def test_default_packing_never_forces_breaks_even_for_heavy_cvs():
    # Lot 1 (2026-11): page breaks follow the measured height in the renderer.
    # The former forced breaks every 21 units produced 6-page CVs filled at 55 %.
    data = {"name": "O", "title": "T", "formations": [], "skills": [], "experiences": [_exp(label, 25) for label in "ABCDEFGHIJ"]}

    options = build_layout_packing_options(data)

    assert options["force_experiences_new_page"] is False
    assert options["force_page_break_before_experience_indexes"] == []
    assert "page_dense_char_threshold" not in options
    assert "anti_crowding" not in options


def test_layout_packing_guard_rejects_content_mutation():
    data = {"name": "O", "title": "T", "formations": [], "skills": [], "experiences": [_exp("A", 2)]}
    payload = copy.deepcopy(data)
    payload["_layout"] = build_layout_packing_options(data)
    payload["experiences"][0]["sections"][0]["content"] = ["Bullet condensé"]

    try:
        assert_packing_preserves_experience_content(data, payload)
    except AssertionError as exc:
        assert "mutated" in str(exc)
    else:
        raise AssertionError("expected layout packing guard to reject mutations")


def test_medium_faithful_cv_does_not_create_sparse_forced_pages():
    data = {
        "name": "OUSSAMA",
        "title": "Technical Leader RPA/IA",
        "formations": [],
        "skills": [{"category": f"Cat {i}", "items": ["A", "B", "C"]} for i in range(18)],
        "experiences": [
            _exp("A", 18),
            _exp("B", 20),
            _exp("C", 20),
            _exp("D", 7),
            _exp("E", 6),
            _exp("F", 7),
            _exp("G", 5),
        ],
    }

    options = build_layout_packing_options(data)

    assert options["force_experiences_new_page"] is False
    assert options["force_page_break_before_experience_indexes"] == []


def test_short_cv_layout_packing_does_not_force_artificial_experience_pages():
    data = {
        "name": "NICOLAS",
        "title": "Responsable du Domaine Applicatif SI Groupe",
        "formations": [],
        "skills": [
            {"category": "Compétences et outils", "items": ["Management d'équipe", "ERP - AS400 DB2 – SAP - ORACLE - D365"]},
            {"category": "Processus métiers", "items": ["Gestion de projets informatiques", "Supply chain"]},
        ],
        "experiences": [_exp("A", 3), _exp("B", 3), _exp("C", 2), _exp("D", 1), _exp("E", 1), _exp("F", 1)],
    }

    options = build_layout_packing_options(data)

    assert options["force_experiences_new_page"] is False
    assert options["force_page_break_before_experience_indexes"] == []
