"""Tests for the worker integration helpers that emit source quality events.

The helpers live next to ``process_job`` in ``src.main``; the tests only
exercise the pure functions so the worker bootstrap does not have to run.
"""
from __future__ import annotations

from src.main import _attach_final_quality_report, _build_source_quality_payload
from src.quality_report import should_require_human_review


def test_build_source_quality_payload_is_redacted_and_classifies_ats():
    text = (
        "Jean Dupont\n"
        "TJM 650\n"
        "Disponibilité immédiate\n"
        "Mobilité Paris\n"
        "Permis B\n"
        "Expériences professionnelles"
    )
    payload = _build_source_quality_payload(
        text, raw_chars=len(text), sanitized_chars=len(text) - 12
    )

    assert payload["source_profile"] == "ats"
    assert payload["metrics"]["raw_chars"] == len(text)
    assert payload["metrics"]["sanitized_chars"] == len(text) - 12
    # Source identity must not leak into the event payload.
    assert "Jean" not in str(payload)
    assert "Dupont" not in str(payload)
    # Extraction score should be set deterministically.
    assert isinstance(payload["scores"]["extraction"], int)
    assert 0 <= payload["scores"]["extraction"] <= 100


def test_build_source_quality_payload_classifies_senior_long():
    text = "\n".join(
        ["EXPÉRIENCES PROFESSIONNELLES"]
        + [f"Mission {i} consultant developpeur 202{i % 10}" for i in range(14)]
    )
    payload = _build_source_quality_payload(text, raw_chars=len(text), sanitized_chars=len(text))
    assert payload["source_profile"] == "senior_long"


def test_attach_final_quality_report_maps_soft_layout_to_quality_summary():
    qa_report = {
        "pages": 3,
        "has_logo": True,
        "has_watermark": True,
        "layout_issues": [
            {"code": "last_page_sparse", "page": 3, "message": "Dernière page trop vide"}
        ],
    }

    updated = _attach_final_quality_report(
        qa_report=qa_report,
        request_id="req_123",
        source_profile="senior_long",
        final_qa_status="draft",
        layout_warnings=qa_report["layout_issues"],
        attempts_count=2,
        total_duration_seconds=12.4,
        fidelity_soft_warnings=["source_fidelity_soft_warning"],
    )

    quality = updated["quality_report"]
    assert quality["source_profile"] == "senior_long"
    assert quality["stage"] == "final"
    assert quality["metrics"]["pages"] == 3
    assert quality["metrics"]["attempts_count"] == 2
    assert {w["code"] for w in quality["soft_warnings"]} == {
        "last_page_sparse",
        "source_fidelity_soft_warning",
    }
    assert quality["hard_blockers"] == []


def test_attach_final_quality_report_records_hard_blocker_on_failed():
    qa_report = {"pages": 1, "has_logo": True, "has_watermark": True, "layout_issues": []}

    updated = _attach_final_quality_report(
        qa_report=qa_report,
        request_id="req_123",
        source_profile="normal",
        final_qa_status="failed",
        layout_warnings=[],
        attempts_count=1,
        total_duration_seconds=5.0,
    )

    quality = updated["quality_report"]
    assert any(b["code"] == "qa_failed" and b["stage"] == "qa" for b in quality["hard_blockers"])


def test_should_require_human_review_short_text():
    assert should_require_human_review({"profile": "scanned", "chars": 80, "line_count": 2}) is True

