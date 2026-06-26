from __future__ import annotations

import pytest

from src.layout.comment_hints import build_layout_revision_options, mentions_move_from_last_page


def _report(*codes: str, page: int | None = None) -> dict:
    return {
        "layout_issues": [
            {"code": code, "page": page or 4} for code in codes
        ]
    }


def test_layout_only_path_returns_compact_grouping_options():
    base_options = {
        "force_experiences_new_page": True,
        "force_page_break_before_experience_indexes": [0],
        "allow_grouping": False,
        "anti_crowding": False,
        "density_profile": "balanced",
        "page_dense_char_threshold": 2800,
        "max_used_ratio": 0.85,
        "readability_reserve": 130,
    }
    comments = [
        "remonter la dernière mission clé de la derniere page sur page 3"
    ]
    qa_report = _report("last_page_sparse")

    options = build_layout_revision_options(
        base_options=base_options,
        previous_qa_report=qa_report,
        comments=comments,
    )

    assert options["force_experiences_new_page"] is False
    assert options["force_page_break_before_experience_indexes"] == []
    assert options["allow_grouping"] is True
    assert options["anti_crowding"] is True
    assert options["density_profile"] == "compact_balanced"
    assert options["page_dense_char_threshold"] >= 3200
    assert options["max_used_ratio"] >= 0.90
    assert options["readability_reserve"] <= 90
    assert options["revision_intent"] == "move_tail_from_sparse_last_page"


def test_layout_only_path_detects_multiple_keywords():
    comments = ["aérer la page 2", "compacter les compétences"]

    # These comments do not contain a move keyword, so no layout-only intent.
    assert not mentions_move_from_last_page(comments)


def test_content_intent_does_not_set_revision_intent():
    base_options = {
        "anti_crowding": False,
        "page_dense_char_threshold": 2800,
        "max_used_ratio": 0.85,
        "readability_reserve": 130,
    }
    comments = ["ajouter l'expérience Thales"]
    qa_report = _report("last_page_sparse")

    options = build_layout_revision_options(
        base_options=base_options,
        previous_qa_report=qa_report,
        comments=comments,
    )

    assert "revision_intent" not in options


def test_no_comments_returns_neutral_options():
    base_options = {
        "anti_crowding": False,
        "force_experiences_new_page": False,
        "force_page_break_before_experience_indexes": [1],
        "allow_grouping": False,
        "density_profile": "balanced",
        "page_dense_char_threshold": 2800,
        "max_used_ratio": 0.85,
        "readability_reserve": 130,
    }
    qa_report = _report("last_page_sparse")

    from src.layout_intelligence import build_layout_retry_options

    expected = build_layout_retry_options(base_options, qa_report)
    actual = build_layout_revision_options(
        base_options=base_options,
        previous_qa_report=qa_report,
        comments=[],
    )

    assert actual == expected
    assert "revision_intent" not in actual


def test_sparse_without_layout_intent_uses_standard_retry():
    base_options = {
        "anti_crowding": False,
        "page_dense_char_threshold": 2800,
        "max_used_ratio": 0.85,
        "readability_reserve": 130,
    }
    comments = ["corrige le texte de la mission"]
    qa_report = _report("last_page_sparse")

    options = build_layout_revision_options(
        base_options=base_options,
        previous_qa_report=qa_report,
        comments=comments,
    )

    # Should fall back to standard retry, not set revision_intent.
    assert "revision_intent" not in options
    assert options["force_experiences_new_page"] is False
    assert options["allow_grouping"] is True
