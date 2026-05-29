import copy

import pytest

from src.layout_retry import assert_layout_retry_preserves_content, is_safe_layout_retry_report


def _report(**overrides):
    report = {
        "layout_issues": [{"code": "page_too_dense", "page": 3}],
        "contact_hits": [],
        "bad_glyphs": False,
        "text_overflow_hits": [],
        "has_logo": True,
        "has_watermark": True,
    }
    report.update(overrides)
    return report


def test_safe_layout_retry_accepts_pure_page_too_dense():
    assert is_safe_layout_retry_report(_report()) is True


def test_safe_layout_retry_rejects_contact_overflow_and_asset_failures():
    assert is_safe_layout_retry_report(_report(contact_hits=["email"])) is False
    assert is_safe_layout_retry_report(_report(text_overflow_hits=[{"page": 2}])) is False
    assert is_safe_layout_retry_report(_report(has_logo=False)) is False
    assert is_safe_layout_retry_report(_report(content_integrity_issues=[{"code": "numbered_placeholder_repetition"}])) is False


def test_safe_layout_retry_accepts_sparse_or_bad_break_for_packing_retry():
    assert is_safe_layout_retry_report(_report(layout_issues=[{"code": "last_page_sparse"}])) is True


def _dense_zahia_like_structured_content():
    return {
        "name": "ZAHIA",
        "title": "Product Owner Assurance",
        "formations": [{"date": "2007", "degree": "Master 2", "school": "Université Paris"}],
        "skills": [
            {"category": "Méthodes", "items": ["Agile", "Scrum", "Gestion backlog"]},
            {"category": "Assurance", "items": ["Prévoyance", "Santé", "Retraite"]},
        ],
        "experiences": [
            {
                "date": "Janvier 2024 – Décembre 2025",
                "role": "Product Owner Assurance – KLESIA",
                "company_highlight": "KLESIA",
                "sections": [
                    {
                        "heading": "Missions clés",
                        "content": [
                            "Analyse des besoins métier prévoyance et santé",
                            "Animation des ateliers avec les parties prenantes",
                            "Rédaction des user stories et critères d'acceptation",
                            "Suivi des anomalies et coordination recette",
                        ],
                    },
                    {
                        "heading": "Environnement technique",
                        "content": ["Jira", "Confluence", "SQL", "API REST"],
                    },
                ],
            },
            {
                "date": "2019 – 2023",
                "role": "Business Analyst Assurance – Client source",
                "company_highlight": "Client source",
                "sections": [
                    {
                        "heading": "Missions clés",
                        "content": [
                            "Cadrage fonctionnel",
                            "Support recette métier",
                        ],
                    }
                ],
            },
        ],
    }


def test_layout_retry_payload_may_add_only_internal_layout_hints():
    structured = _dense_zahia_like_structured_content()
    retry_payload = copy.deepcopy(structured)
    retry_payload["_layout"] = {
        "anti_crowding": True,
        "page_dense_char_threshold": 2800,
        "max_used_ratio": 0.80,
        "readability_reserve": 170,
    }

    assert_layout_retry_preserves_content(structured, retry_payload)


def test_layout_retry_payload_rejects_unauthorized_content_compaction():
    structured = _dense_zahia_like_structured_content()
    retry_payload = copy.deepcopy(structured)
    retry_payload["_layout"] = {"anti_crowding": True}
    retry_payload["experiences"][0]["sections"][0]["content"] = [
        "Analyse des besoins, ateliers, user stories et recette"
    ]

    with pytest.raises(AssertionError, match="mutated structured content"):
        assert_layout_retry_preserves_content(structured, retry_payload)
