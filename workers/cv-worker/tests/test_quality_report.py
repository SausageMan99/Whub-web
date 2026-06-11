"""Tests for the redacted CV quality report builder.

These tests are intentionally light and focus on the safety contract of the
quality report module: it must never embed raw contact-like values and it must
classify the source profile deterministically based on the source text alone.
"""
from __future__ import annotations

import pytest

from src.quality_report import (
    QualityReportBuilder,
    assert_quality_report_is_redacted,
    classify_source_profile,
    should_require_human_review,
)


def test_quality_report_builder_records_scores_and_redacted_metrics():
    builder = QualityReportBuilder(request_id="req_123")
    builder.set_source_profile("senior_long")
    builder.add_score("extraction", 82)
    builder.add_score("fidelity", 91)
    builder.add_metric("raw_chars", 12000)
    builder.add_metric("pages", 4)
    builder.add_soft_warning("last_page_sparse", stage="layout", page=4)

    report = builder.to_dict(stage="final")

    assert report["schema_version"] == 1
    assert report["source_profile"] == "senior_long"
    assert report["stage"] == "final"
    assert report["scores"]["extraction"] == 82
    assert report["scores"]["fidelity"] == 91
    assert report["metrics"]["raw_chars"] == 12000
    assert report["metrics"]["pages"] == 4
    assert report["soft_warnings"] == [
        {"code": "last_page_sparse", "stage": "layout", "page": 4}
    ]
    assert report["hard_blockers"] == []
    assert report["redaction"]["contains_raw_contact_values"] is False
    assert report["redaction"]["contains_source_snippets"] is False


def test_quality_report_blocks_contact_like_values_in_payload():
    bad = {
        "hard_blockers": [
            {"code": "contact_leak", "stage": "structuring", "value": "test@example.com"}
        ],
        "soft_warnings": [],
        "metrics": {},
    }

    with pytest.raises(ValueError, match="raw contact"):
        assert_quality_report_is_redacted(bad)


def test_classify_source_profile_detects_senior_long_and_ats():
    senior_text = "\n".join(
        ["EXPÉRIENCES PROFESSIONNELLES"]
        + [f"Mission {i} consultant developpeur 202{i % 10}" for i in range(14)]
    )
    ats_text = (
        "Disponibilité immédiate\n"
        "TJM 650\n"
        "Mobilité Paris\n"
        "Permis B\n"
        "Expériences professionnelles"
    )

    assert classify_source_profile(senior_text)["profile"] == "senior_long"
    assert classify_source_profile(ats_text)["profile"] == "ats"


def test_should_require_human_review_for_scanned_or_tiny_extraction():
    assert should_require_human_review({"profile": "scanned", "chars": 120, "line_count": 3}) is True


def test_should_not_require_human_review_for_normal_text():
    assert (
        should_require_human_review({"profile": "normal", "chars": 2500, "line_count": 80})
        is False
    )
