from pathlib import Path

import pytest

from src import storage
from tests.test_draft_ready import _FakeClient, _report


def _write_draft_pdf(tmp_path: Path) -> Path:
    pdf = tmp_path / "draft.pdf"
    pdf.write_bytes(b"%PDF draft")
    return pdf


def test_ready_with_passed_missing_raises(monkeypatch, tmp_path):
    fake_client = _FakeClient()
    monkeypatch.setattr(storage, "client", fake_client)
    pdf = _write_draft_pdf(tmp_path)

    with pytest.raises(ValueError, match="ready requests require qa_report.passed=true"):
        storage.save_version(
            "request-1",
            {"name": "ZAHIA", "experiences": []},
            pdf,
            _report(passed=False, layout_issues=[{"code": "page_too_dense", "page": 2}], extra_key=True),
            request_status="ready",
            qa_status="passed",
            owner="test-owner",
        )


def test_ready_with_passed_false_raises(monkeypatch, tmp_path):
    fake_client = _FakeClient()
    monkeypatch.setattr(storage, "client", fake_client)
    pdf = _write_draft_pdf(tmp_path)

    with pytest.raises(ValueError, match="ready requests require qa_report.passed=true"):
        storage.save_version(
            "request-1",
            {"name": "ZAHIA", "experiences": []},
            pdf,
            _report(passed=False, layout_issues=[{"code": "page_too_dense", "page": 2}]),
            request_status="ready",
            qa_status="passed",
            owner="test-owner",
        )


def test_ready_with_passed_true_passes_guard(monkeypatch, tmp_path):
    fake_client = _FakeClient()
    monkeypatch.setattr(storage, "client", fake_client)
    pdf = _write_draft_pdf(tmp_path)

    version = storage.save_version(
        "request-1",
        {"name": "ZAHIA", "experiences": []},
        pdf,
        _report(passed=True),
        request_status="ready",
        qa_status="passed",
        owner="test-owner",
    )

    assert version == {"id": "version-1", "version_number": 3}


def test_draft_ready_with_passed_true_raises(monkeypatch, tmp_path):
    fake_client = _FakeClient()
    monkeypatch.setattr(storage, "client", fake_client)
    pdf = _write_draft_pdf(tmp_path)

    with pytest.raises(ValueError, match="draft_ready requests must carry a non-passing QA report"):
        storage.save_version(
            "request-1",
            {"name": "ZAHIA", "experiences": []},
            pdf,
            _report(passed=True),
            request_status="draft_ready",
            qa_status="draft",
            owner="test-owner",
        )


def test_draft_ready_with_passed_missing_passes_guard(monkeypatch, tmp_path):
    fake_client = _FakeClient()
    monkeypatch.setattr(storage, "client", fake_client)
    pdf = _write_draft_pdf(tmp_path)

    version = storage.save_version(
        "request-1",
        {"name": "ZAHIA", "experiences": []},
        pdf,
        _report(passed=False, pages=5),
        request_status="draft_ready",
        qa_status="draft",
        owner="test-owner",
    )

    assert version == {"id": "version-1", "version_number": 3}


def test_draft_ready_with_passed_false_passes_guard(monkeypatch, tmp_path):
    fake_client = _FakeClient()
    monkeypatch.setattr(storage, "client", fake_client)
    pdf = _write_draft_pdf(tmp_path)

    version = storage.save_version(
        "request-1",
        {"name": "ZAHIA", "experiences": []},
        pdf,
        _report(passed=False, layout_issues=[{"code": "page_too_dense", "page": 2}]),
        request_status="draft_ready",
        qa_status="draft",
        owner="test-owner",
    )

    assert version == {"id": "version-1", "version_number": 3}


def test_draft_override_of_passing_report_is_accepted_by_save_version(monkeypatch, tmp_path):
    # Regression (Heidi, 2026-11-02): QA passed but fidelity soft warnings forced
    # draft_ready, and save_version rejected the still-passing report.
    from src.main import _mark_qa_report_draft_override

    fake_client = _FakeClient()
    monkeypatch.setattr(storage, "client", fake_client)
    pdf = _write_draft_pdf(tmp_path)
    original = _report(passed=True)

    overridden = _mark_qa_report_draft_override(original, "fidelity_soft_warnings")

    assert original["passed"] is True
    assert overridden["passed"] is False
    assert overridden["draft_override_reason"] == "fidelity_soft_warnings"
    version = storage.save_version(
        "request-1",
        {"name": "ZAHIA", "experiences": []},
        pdf,
        overridden,
        request_status="draft_ready",
        qa_status="draft",
        owner="test-owner",
    )
    assert version == {"id": "version-1", "version_number": 3}
