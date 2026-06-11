"""Tests for the offline CV evaluation runner."""
from __future__ import annotations

from eval.run_eval import evaluate_case_result


def test_evaluate_case_result_passes_expected_terms_and_forbidden_patterns():
    case = {
        "id": "case1",
        "assertions": {
            "expected_status": "ready",
            "required_terms": ["React", "AWS"],
            "forbidden_patterns": ["@", "linkedin.com"],
            "max_pages": 3,
            "disallowed_qa_codes": ["contact_leak"],
        },
    }
    result = {
        "status": "ready",
        "pdf_text": "Architecte React AWS chez un client grand compte",
        "qa_report": {"pages": 2, "layout_issues": []},
    }

    verdict = evaluate_case_result(case, result)

    assert verdict["passed"] is True
    assert verdict["failures"] == []


def test_evaluate_case_result_fails_on_forbidden_pattern():
    case = {"id": "case1", "assertions": {"forbidden_patterns": ["@"]}}
    result = {"status": "ready", "pdf_text": "contact test@example.com", "qa_report": {"pages": 1}}

    verdict = evaluate_case_result(case, result)

    assert verdict["passed"] is False
    assert "forbidden_pattern:@" in verdict["failures"]


def test_evaluate_case_result_fails_on_disallowed_layout_code():
    case = {
        "id": "case1",
        "assertions": {"disallowed_qa_codes": ["contact_leak"]},
    }
    result = {
        "status": "qa_failed",
        "pdf_text": "CV",
        "qa_report": {
            "pages": 1,
            "layout_issues": [{"code": "contact_leak", "page": 1, "message": "x"}],
        },
    }

    verdict = evaluate_case_result(case, result)

    assert verdict["passed"] is False
    assert "disallowed_qa_code:contact_leak" in verdict["failures"]


def test_evaluate_case_result_fails_on_max_pages():
    case = {
        "id": "case1",
        "assertions": {"max_pages": 2},
    }
    result = {
        "status": "ready",
        "pdf_text": "CV",
        "qa_report": {"pages": 4, "layout_issues": []},
    }

    verdict = evaluate_case_result(case, result)

    assert verdict["passed"] is False
    assert any(f.startswith("pages:") for f in verdict["failures"])


def test_evaluate_case_result_no_assertions_always_passes():
    case = {"id": "case1", "assertions": {}}
    result = {"status": "ready", "pdf_text": "anything", "qa_report": {"pages": 1}}

    verdict = evaluate_case_result(case, result)

    assert verdict["passed"] is True
    assert verdict["failures"] == []
