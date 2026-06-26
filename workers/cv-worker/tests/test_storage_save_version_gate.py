from pathlib import Path

import pytest

from src import storage
from tests.test_draft_ready import (
    _FakeClient,
    _report,
)


def test_save_version_rejects_ready_when_qa_report_passed_is_false(monkeypatch, tmp_path):
    fake_client = _FakeClient()
    monkeypatch.setattr(storage, "client", fake_client)
    pdf_path = tmp_path / "draft.pdf"
    pdf_path.write_bytes(b"%PDF draft")

    with pytest.raises(ValueError, match="qa_report.passed"):
        storage.save_version(
            "request-1",
            {"name": "ZAHIA", "experiences": []},
            pdf_path,
            _report(passed=False, layout_issues=[{"code": "page_too_dense", "page": 2}]),
            request_status="ready",
            qa_status="passed",
            owner="test-owner",
        )


def test_save_version_rejects_draft_ready_when_qa_report_passed_is_true(monkeypatch, tmp_path):
    fake_client = _FakeClient()
    monkeypatch.setattr(storage, "client", fake_client)
    pdf_path = tmp_path / "draft.pdf"
    pdf_path.write_bytes(b"%PDF draft")

    with pytest.raises(ValueError):
        storage.save_version(
            "request-1",
            {"name": "ZAHIA", "experiences": []},
            pdf_path,
            _report(passed=True),
            request_status="draft_ready",
            qa_status="draft",
            owner="test-owner",
        )
