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
