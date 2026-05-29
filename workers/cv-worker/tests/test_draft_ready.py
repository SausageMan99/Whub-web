from unittest.mock import Mock

import pytest

from src.qa import classify_qa_report
from src.qa import QAError
from src import main as worker_main
from src import storage


def _report(**overrides):
    report = {
        "passed": False,
        "pages": 2,
        "contact_hits": [],
        "bad_glyphs": False,
        "content_integrity_issues": [],
        "text_overflow_hits": [],
        "layout_issues": [],
        "has_logo": True,
        "has_watermark": True,
    }
    report.update(overrides)
    return report


def test_classify_qa_report_soft_layout_only_returns_draft_with_warnings():
    report = _report(layout_issues=[{"code": "page_too_dense", "page": 2}, {"code": "skills_too_dense", "page": 1}])

    status, warnings = classify_qa_report(report)

    assert status == "draft"
    assert warnings == report["layout_issues"]


@pytest.mark.parametrize(
    "overrides",
    [
        {"contact_hits": ["email"]},
        {"contact_hits": ["forbidden_name:Dupont"]},
        {"text_overflow_hits": [{"page": 2}]},
        {"content_integrity_issues": [{"code": "json_fact_missing_from_pdf"}]},
        {"bad_glyphs": True},
        {"has_logo": False},
        {"has_watermark": False},
        {"pages": 0},
    ],
)
def test_classify_qa_report_mixed_hard_and_soft_returns_failed(overrides):
    report = _report(layout_issues=[{"code": "page_too_dense", "page": 2}], **overrides)

    status, warnings = classify_qa_report(report)

    assert status == "failed"
    assert warnings == []


def test_classify_qa_report_passed_when_no_issues():
    status, warnings = classify_qa_report(_report(passed=True))

    assert status == "passed"
    assert warnings == []


def test_classify_qa_report_unknown_layout_code_is_failed():
    status, warnings = classify_qa_report(_report(layout_issues=[{"code": "mystery_layout_issue", "page": 1}]))

    assert status == "failed"
    assert warnings == []


class _FakeStorageBucket:
    def __init__(self, uploads):
        self.uploads = uploads

    def upload(self, path, data, options):
        self.uploads.append({"path": path, "data": data, "options": options})


class _FakeStorageRoot:
    def __init__(self, uploads):
        self.uploads = uploads

    def from_(self, bucket):
        return _FakeStorageBucket(self.uploads)


class _FakeQuery:
    def __init__(self, client, table, operation, payload=None):
        self.client = client
        self.table = table
        self.operation = operation
        self.payload = payload
        self.filters = []

    def eq(self, field, value):
        self.filters.append((field, value))
        return self

    def execute(self):
        self.client.operations.append({
            "table": self.table,
            "operation": self.operation,
            "payload": self.payload,
            "filters": self.filters,
        })
        if self.table == "cv_versions" and self.operation == "insert":
            return type("Res", (), {"data": [{"id": "version-1"}]})()
        return type("Res", (), {"data": []})()


class _FakeTable:
    def __init__(self, client, table):
        self.client = client
        self.table = table

    def insert(self, payload):
        return _FakeQuery(self.client, self.table, "insert", payload)

    def update(self, payload):
        return _FakeQuery(self.client, self.table, "update", payload)


class _FakeClient:
    def __init__(self):
        self.operations = []
        self.uploads = []
        self.storage = _FakeStorageRoot(self.uploads)

    def table(self, table):
        return _FakeTable(self, table)


def test_save_version_persists_draft_status_and_full_qa_report(monkeypatch, tmp_path):
    fake_client = _FakeClient()
    monkeypatch.setattr(storage, "client", fake_client)
    pdf_path = tmp_path / "draft.pdf"
    pdf_path.write_bytes(b"%PDF draft")
    qa_report = _report(layout_issues=[{"code": "page_too_dense", "page": 2, "message": "Page dense"}])

    version_id = storage.save_version(
        "request-1",
        3,
        {"name": "ZAHIA", "experiences": []},
        pdf_path,
        qa_report,
        request_status="draft_ready",
        qa_status="draft",
    )

    assert version_id == "version-1"
    version_insert = next(op for op in fake_client.operations if op["table"] == "cv_versions")
    request_update = next(op for op in fake_client.operations if op["table"] == "cv_requests")
    assert version_insert["payload"]["qa_status"] == "draft"
    assert version_insert["payload"]["qa_report"] == qa_report
    assert request_update["payload"]["status"] == "draft_ready"
    assert request_update["payload"]["current_version_id"] == "version-1"
    assert request_update["payload"]["last_error"] is None


@pytest.mark.parametrize(
    "request_status,qa_status",
    [("qa_failed", "draft"), ("draft_ready", "failed")],
)
def test_save_version_rejects_unsafe_status_pairs(tmp_path, request_status, qa_status):
    pdf_path = tmp_path / "draft.pdf"
    pdf_path.write_bytes(b"%PDF draft")

    with pytest.raises(ValueError):
        storage.save_version("request-1", 1, {}, pdf_path, _report(), request_status=request_status, qa_status=qa_status)


def test_process_job_soft_layout_after_retry_saves_draft_ready(monkeypatch, tmp_path):
    saved = {}
    events = []
    report = _report(layout_issues=[{"code": "page_too_dense", "page": 2, "message": "Page dense"}])
    pdf_path = tmp_path / "output.pdf"
    pdf_path.write_bytes(b"%PDF draft")

    monkeypatch.setattr(worker_main.settings, "tmp_dir", str(tmp_path))
    monkeypatch.setattr(worker_main, "download_source", lambda job, workdir: pdf_path)
    monkeypatch.setattr(worker_main, "extract_pdf_text", lambda source: "Zahia source")
    monkeypatch.setattr(worker_main, "build_whub_json", lambda *args: {"name": "ZAHIA", "formations": [], "skills": [], "experiences": []})
    monkeypatch.setattr(worker_main, "assert_no_contact_in_json", lambda structured: None)
    monkeypatch.setattr(worker_main, "enforce_client_first_name", lambda structured, first_name: None)
    monkeypatch.setattr(worker_main, "next_version_number", lambda request_id: 1)
    monkeypatch.setattr(worker_main, "render_pdf", lambda *args, **kwargs: pdf_path)
    monkeypatch.setattr(worker_main, "run_qa", Mock(side_effect=QAError(report)))
    monkeypatch.setattr(worker_main, "emit_event", lambda request_id, event, payload=None: events.append((event, payload or {})))
    monkeypatch.setattr(worker_main, "save_version", lambda *args, **kwargs: saved.update({"args": args, "kwargs": kwargs}) or "version-1")

    class _CommentsTable:
        def select(self, *_args): return self
        def update(self, *_args, **_kwargs): return self
        def eq(self, *_args): return self
        def execute(self): return type("Res", (), {"data": []})()

    monkeypatch.setattr(worker_main.client, "table", lambda table: _CommentsTable())

    worker_main.process_job({"id": "request-1", "candidate_first_name": "ZAHIA", "instructions": ""})

    assert saved["kwargs"] == {"request_status": "draft_ready", "qa_status": "draft"}
    assert saved["args"][4] == report
    assert ("draft_ready", {"version_id": "version-1", "version_number": 1, "layout_warnings": report["layout_issues"]}) in events


def test_process_job_mixed_hard_and_soft_blocks_as_qa_failed(monkeypatch, tmp_path):
    failures = []
    report = _report(contact_hits=["email"], layout_issues=[{"code": "page_too_dense", "page": 2}])
    pdf_path = tmp_path / "output.pdf"
    pdf_path.write_bytes(b"%PDF bad")

    monkeypatch.setattr(worker_main.settings, "tmp_dir", str(tmp_path))
    monkeypatch.setattr(worker_main, "download_source", lambda job, workdir: pdf_path)
    monkeypatch.setattr(worker_main, "extract_pdf_text", lambda source: "Zahia source")
    monkeypatch.setattr(worker_main, "build_whub_json", lambda *args: {"name": "ZAHIA", "formations": [], "skills": [], "experiences": []})
    monkeypatch.setattr(worker_main, "assert_no_contact_in_json", lambda structured: None)
    monkeypatch.setattr(worker_main, "enforce_client_first_name", lambda structured, first_name: None)
    monkeypatch.setattr(worker_main, "next_version_number", lambda request_id: 1)
    monkeypatch.setattr(worker_main, "render_pdf", lambda *args, **kwargs: pdf_path)
    monkeypatch.setattr(worker_main, "run_qa", Mock(side_effect=QAError(report)))
    monkeypatch.setattr(worker_main, "fail_job", lambda job, error, status="failed": failures.append((error, status)))
    monkeypatch.setattr(worker_main, "emit_event", lambda *args, **kwargs: None)

    class _CommentsTable:
        def select(self, *_args): return self
        def eq(self, *_args): return self
        def execute(self): return type("Res", (), {"data": []})()

    monkeypatch.setattr(worker_main.client, "table", lambda table: _CommentsTable())

    worker_main.process_job({"id": "request-1", "candidate_first_name": "ZAHIA", "instructions": ""})

    assert failures == [(str(report), "qa_failed")]
