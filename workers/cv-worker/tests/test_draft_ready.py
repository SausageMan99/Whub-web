from unittest.mock import Mock

import pytest

from src.qa import classify_qa_report
from src.qa import QAError
from src import main as worker_main
from src import storage
from src.layout import LayoutResult
from src.layout import run_layout


_MINIMAL_CV_SOURCE = "\n".join(
    [
        "Zahia source",
        "Compétences: Python, Kubernetes, Terraform, conduite du changement, architecture cloud.",
        "Expériences: pilotage de projets data et industrialisation de plateformes internes.",
        "Réalisations: migration applicative, automatisation CI/CD, sécurisation des déploiements.",
        "Formation: école d'ingénieur, certifications cloud, ateliers agiles et mentorat technique.",
        "Langues: français, anglais professionnel, communication avec équipes produit et métier.",
    ]
)


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


def test_classify_qa_report_marked_layout_hard_failure_returns_draft():
    report = _report(
        layout_issues=[{"code": "mystery_layout_issue", "page": 1}],
        _draft_ready_for_layout_hard_failure=True,
    )

    status, warnings = classify_qa_report(report)

    assert status == "draft"
    assert warnings == report["layout_issues"]


def test_classify_qa_report_marked_content_integrity_failure_returns_draft():
    report = _report(
        content_integrity_issues=[{"code": "json_fact_missing_from_pdf", "page": 2}],
        _draft_ready_for_layout_hard_failure=True,
    )

    status, warnings = classify_qa_report(report)

    assert status == "draft"
    assert warnings == report["content_integrity_issues"]


def test_run_layout_returns_draft_candidate_for_pure_layout_hard_failure(tmp_path):
    def fake_render(_structured, _workdir, layout_options=None, output_name="output.pdf"):
        pdf = tmp_path / output_name
        pdf.write_bytes(b"%PDF")
        return pdf

    def fake_run_qa(*_args, **_kwargs):
        raise QAError(_report(layout_issues=[{"code": "mystery_layout_issue", "page": 1}]))

    result = run_layout(
        structured={"name": "HASSANE", "formations": [], "skills": [], "experiences": []},
        workdir=tmp_path,
        render_pdf=fake_render,
        run_qa=fake_run_qa,
        max_attempts=1,
    )

    status, warnings = classify_qa_report(result.qa_report)
    assert status == "draft"
    assert warnings == [{"code": "mystery_layout_issue", "page": 1}]
    assert result.pdf.exists()


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
            return type("Res", (), {"data": [{"id": "version-1", "version_number": 3}]})()
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

    version = storage.save_version(
        "request-1",
        {"name": "ZAHIA", "experiences": []},
        pdf_path,
        qa_report,
        request_status="draft_ready",
        qa_status="draft",
        owner="test-owner",
    )

    assert version == {"id": "version-1", "version_number": 3}
    version_insert = next(op for op in fake_client.operations if op["table"] == "cv_versions")
    request_update = next(op for op in fake_client.operations if op["table"] == "cv_requests")
    assert "version_number" not in version_insert["payload"]
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
        storage.save_version("request-1", {}, pdf_path, _report(), request_status=request_status, qa_status=qa_status, owner="test-owner")


def test_save_version_treats_renderer_input_upload_as_non_blocking(monkeypatch, tmp_path):
    class FailingRendererInputBucket(_FakeStorageBucket):
        def __init__(self, uploads, bucket):
            super().__init__(uploads)
            self.bucket = bucket

        def upload(self, path, data, options):
            if self.bucket == "cv-renderer-inputs":
                raise RuntimeError("storage 400")
            self.uploads.append({"bucket": self.bucket, "path": path, "data": data, "options": options})

    class FailingRendererInputStorageRoot:
        def __init__(self, uploads):
            self.uploads = uploads

        def from_(self, bucket):
            return FailingRendererInputBucket(self.uploads, bucket)

    fake_client = _FakeClient()
    fake_client.storage = FailingRendererInputStorageRoot(fake_client.uploads)
    monkeypatch.setattr(storage, "client", fake_client)
    pdf_path = tmp_path / "ready.pdf"
    pdf_path.write_bytes(b"%PDF ready")

    version = storage.save_version(
        "request-1",
        {"name": "Oussama", "experiences": []},
        pdf_path,
        _report(passed=True),
        request_status="ready",
        qa_status="passed",
        owner="test-owner",
    )

    assert version == {"id": "version-1", "version_number": 3}
    request_update = next(op for op in fake_client.operations if op["table"] == "cv_requests")
    version_update = [op for op in fake_client.operations if op["table"] == "cv_versions" and op["operation"] == "update"][-1]
    assert request_update["payload"]["status"] == "ready"
    assert request_update["payload"]["current_version_id"] == "version-1"
    assert request_update["payload"]["last_error"] is None
    assert version_update["payload"]["renderer_input_path"] is None
    assert version_update["payload"]["final_pdf_path"] == "request-1/v3/cv-whub.pdf"
    assert {u["bucket"] for u in fake_client.uploads} == {"cv-finals", "cv-artifacts"}


def test_process_job_soft_layout_after_retry_saves_draft_ready(monkeypatch, tmp_path):
    saved = {}
    events = []
    report = _report(layout_issues=[{"code": "page_too_dense", "page": 2, "message": "Page dense"}])
    pdf_path = tmp_path / "output.pdf"
    pdf_path.write_bytes(b"%PDF draft")

    monkeypatch.setattr(worker_main.settings, "tmp_dir", str(tmp_path))
    monkeypatch.setattr(worker_main.settings, "worker_name", "whub-cv-worker-hermes-local")
    monkeypatch.setattr(worker_main, "download_source", lambda job, workdir: pdf_path)
    monkeypatch.setattr(worker_main, "extract_pdf_text", lambda source: _MINIMAL_CV_SOURCE)
    monkeypatch.setattr(worker_main, "build_whub_json", lambda *args: {"name": "ZAHIA", "formations": [], "skills": [], "experiences": []})
    monkeypatch.setattr(worker_main, "assert_no_contact_in_json", lambda structured: None)
    monkeypatch.setattr(worker_main, "enforce_client_first_name", lambda structured, first_name: None)
    monkeypatch.setattr(worker_main, "render_pdf", lambda *args, **kwargs: pdf_path)
    monkeypatch.setattr(worker_main, "run_qa", Mock(side_effect=QAError(report)))
    monkeypatch.setattr(worker_main, "emit_event", lambda request_id, event, payload=None: events.append((event, payload or {})))
    monkeypatch.setattr(worker_main, "save_version", lambda *args, **kwargs: saved.update({"args": args, "kwargs": kwargs}) or {"id": "version-1", "version_number": 1})

    class _CommentsTable:
        def select(self, *_args): return self
        def update(self, *_args, **_kwargs): return self
        def eq(self, *_args): return self
        def execute(self): return type("Res", (), {"data": []})()

    monkeypatch.setattr(worker_main.client, "table", lambda table: _CommentsTable())

    def _mock_run_layout(**kwargs):
        return LayoutResult(
            pdf=pdf_path,
            qa_report=report,
            layout_options=kwargs.get("base_options", {}),
            attempts_count=2,
            selected_variant="layout_retry",
        )

    monkeypatch.setattr(worker_main, "run_layout", _mock_run_layout)

    worker_main.process_job({"id": "request-1", "candidate_first_name": "ZAHIA", "instructions": ""})

    expected_kwargs = {"request_status": "draft_ready", "qa_status": "draft", "owner": "whub-cv-worker-hermes-local"}
    assert saved["kwargs"] == expected_kwargs
    saved_qa_report = saved["args"][3]
    # Original report fields must be preserved.
    for key, value in report.items():
        assert saved_qa_report[key] == value
    # New auto-evaluation loop must have attached a redacted quality_report.
    assert isinstance(saved_qa_report["quality_report"], dict)
    assert saved_qa_report["quality_report"]["source_profile"] in {
        "normal",
        "senior_long",
        "ats",
        "scanned",
        "two_column",
        "graphic",
        "risky",
        "unknown",
    }
    assert saved_qa_report["quality_report"]["stage"] == "final"
    assert saved_qa_report["quality_report"]["metrics"]["attempts_count"] == 2
    assert {w["code"] for w in saved_qa_report["quality_report"]["soft_warnings"]} >= {
        "page_too_dense"
    }
    assert (
        "draft_ready",
        {"version_id": "version-1", "version_number": 1, "layout_warnings": report["layout_issues"]},
    ) in events


def test_process_job_soft_fidelity_warnings_save_draft_ready(monkeypatch, tmp_path):
    saved = {}
    events = []
    pdf_path = tmp_path / "output.pdf"
    pdf_path.write_bytes(b"%PDF draft")

    structured = {
        "name": "FRANCK",
        "formations": [],
        "skills": [],
        "experiences": [],
        "_fidelity_soft_warnings": [
            {"code": "experience_content_rewritten_or_absent_from_source", "message": "Reformulation détectée"},
        ],
    }

    monkeypatch.setattr(worker_main.settings, "tmp_dir", str(tmp_path))
    monkeypatch.setattr(worker_main.settings, "worker_name", "whub-cv-worker-hermes-local")
    monkeypatch.setattr(worker_main, "download_source", lambda job, workdir: pdf_path)
    monkeypatch.setattr(worker_main, "extract_pdf_text", lambda source: _MINIMAL_CV_SOURCE)
    monkeypatch.setattr(worker_main, "build_whub_json", lambda *args: structured.copy())
    monkeypatch.setattr(worker_main, "assert_no_contact_in_json", lambda structured: None)
    monkeypatch.setattr(worker_main, "enforce_client_first_name", lambda structured, first_name: None)
    monkeypatch.setattr(worker_main, "render_pdf", lambda *args, **kwargs: pdf_path)
    monkeypatch.setattr(worker_main, "run_qa", Mock(return_value=_report()))
    monkeypatch.setattr(worker_main, "emit_event", lambda request_id, event, payload=None: events.append((event, payload or {})))
    monkeypatch.setattr(worker_main, "save_version", lambda *args, **kwargs: saved.update({"args": args, "kwargs": kwargs}) or {"id": "version-1", "version_number": 1})

    class _CommentsTable:
        def select(self, *_args): return self
        def update(self, *_args, **_kwargs): return self
        def eq(self, *_args): return self
        def execute(self): return type("Res", (), {"data": []})()

    monkeypatch.setattr(worker_main.client, "table", lambda table: _CommentsTable())

    worker_main.process_job({"id": "request-1", "candidate_first_name": "FRANCK", "instructions": ""})

    assert saved["kwargs"] == {"request_status": "draft_ready", "qa_status": "draft", "owner": "whub-cv-worker-hermes-local"}
    quality = saved["args"][3]["quality_report"]
    assert {w["code"] for w in quality["soft_warnings"]} >= {"experience_content_rewritten_or_absent_from_source"}
    assert (
        "draft_ready",
        {
            "version_id": "version-1",
            "version_number": 1,
            "layout_warnings": [],
            "fidelity_warnings": [{"code": "experience_content_rewritten_or_absent_from_source", "message": "Reformulation détectée"}],
        },
    ) in events


def test_process_job_revision_includes_previous_version_history(monkeypatch, tmp_path):
    captured = {}
    pdf_path = tmp_path / "revision.pdf"
    pdf_path.write_bytes(b"%PDF draft")

    monkeypatch.setattr(worker_main.settings, "tmp_dir", str(tmp_path))
    monkeypatch.setattr(worker_main, "download_source", lambda job, workdir: pdf_path)
    monkeypatch.setattr(worker_main, "extract_pdf_text", lambda source: _MINIMAL_CV_SOURCE)
    monkeypatch.setattr(worker_main, "build_whub_json", lambda text, instructions, comments, candidate_first_name: captured.update({"comments": comments, "instructions": instructions}) or {"name": "ZAHIA", "formations": [], "skills": [], "experiences": []})
    monkeypatch.setattr(worker_main, "assert_no_contact_in_json", lambda structured: None)
    monkeypatch.setattr(worker_main, "enforce_client_first_name", lambda structured, first_name: None)
    monkeypatch.setattr(worker_main, "render_pdf", lambda *args, **kwargs: pdf_path)
    monkeypatch.setattr(worker_main, "run_qa", Mock(return_value=_report()))
    monkeypatch.setattr(worker_main, "save_version", lambda *args, **kwargs: {"id": "version-2", "version_number": 2})
    monkeypatch.setattr(worker_main, "emit_event", lambda *args, **kwargs: None)

    class _Table:
        def __init__(self, table: str):
            self.table = table

        def select(self, *_args):
            return self

        def eq(self, *_args):
            return self

        def update(self, *_args, **_kwargs):
            return self

        def execute(self):
            if self.table == "cv_comments":
                return type("Res", (), {"data": [{"body": "Recrée la V2", "comment_type": "revision"}]})()
            if self.table == "cv_versions":
                return type("Res", (), {"data": [{"version_number": 1, "qa_status": "draft", "qa_report": {"layout_issues": [{"code": "page_too_dense", "message": "Page dense"}]}}]})()
            return type("Res", (), {"data": []})()

    monkeypatch.setattr(worker_main.client, "table", lambda table: _Table(table))

    worker_main.process_job({"id": "request-1", "current_version_id": "version-1", "candidate_first_name": "ZAHIA", "instructions": "Corrige la page 2"})

    assert captured["instructions"] == "Corrige la page 2"
    assert captured["comments"][0]["comment_type"] == "history"
    assert "Historique utile: version V1 (qa=draft)." in captured["comments"][0]["body"]
    assert "page_too_dense" in captured["comments"][0]["body"]
def test_process_job_mixed_hard_and_soft_blocks_as_qa_failed(monkeypatch, tmp_path):
    failures = []
    report = _report(contact_hits=["email"], layout_issues=[{"code": "page_too_dense", "page": 2}])
    pdf_path = tmp_path / "output.pdf"
    pdf_path.write_bytes(b"%PDF bad")

    monkeypatch.setattr(worker_main.settings, "tmp_dir", str(tmp_path))
    monkeypatch.setattr(worker_main, "download_source", lambda job, workdir: pdf_path)
    monkeypatch.setattr(worker_main, "extract_pdf_text", lambda source: _MINIMAL_CV_SOURCE)
    monkeypatch.setattr(worker_main, "build_whub_json", lambda *args: {"name": "ZAHIA", "formations": [], "skills": [], "experiences": []})
    monkeypatch.setattr(worker_main, "assert_no_contact_in_json", lambda structured: None)
    monkeypatch.setattr(worker_main, "enforce_client_first_name", lambda structured, first_name: None)
    monkeypatch.setattr(worker_main, "render_pdf", lambda *args, **kwargs: pdf_path)
    monkeypatch.setattr(worker_main, "run_qa", Mock(side_effect=QAError(report)))
    monkeypatch.setattr(worker_main, "fail_job", lambda job, error, status="failed": failures.append((error, status)))
    monkeypatch.setattr(worker_main, "emit_event", lambda *args, **kwargs: None)

    class _CommentsTable:
        def select(self, *_args): return self
        def eq(self, *_args): return self
        def execute(self): return type("Res", (), {"data": []})()

    monkeypatch.setattr(worker_main.client, "table", lambda table: _CommentsTable())

    def _mock_run_layout(**kwargs):
        # Replicate the original behavior: fail_job receives str(qa_report)
        raise RuntimeError(str(report))

    monkeypatch.setattr(worker_main, "run_layout", _mock_run_layout)

    worker_main.process_job({"id": "request-1", "candidate_first_name": "ZAHIA", "instructions": ""})

    assert failures == [(str(report), "qa_failed")]


def test_process_job_sanitizes_source_text_before_structuring(monkeypatch, tmp_path):
    raw_text = "\n".join(
        [
            "Jean Dupont",
            "jean@example.com",
            "06 12 34 56 78",
            "linkedin.com/in/jean",
            "CV téléchargé depuis Hellowork",
            "Compétences: Python, Kubernetes, Terraform, AWS, CI/CD, sécurité applicative.",
            "Expériences: architecte cloud chez un grand client retail, migration Kubernetes.",
            "Réalisations: automatisation des déploiements, observabilité, coaching des équipes.",
            "Projets: refonte plateforme data, optimisation coûts cloud, gouvernance DevOps.",
            "Formation: master informatique, certifications cloud, pratiques agiles avancées.",
            "Langues: français, anglais professionnel, animation d'ateliers avec les métiers.",
        ]
    )
    pdf_path = tmp_path / "sanitized.pdf"
    pdf_path.write_bytes(b"%PDF sanitized")
    captured = {}
    events = []

    def _build_whub_json(text, instructions, comments, candidate_first_name):
        captured["structured_text"] = text
        return {"name": "JEAN", "formations": [], "skills": [], "experiences": []}

    def _forbidden(candidate_first_name, source_text=None):
        captured["forbidden_args"] = (candidate_first_name, source_text)
        return []

    def _mock_run_layout(**kwargs):
        captured["layout_source_text"] = kwargs.get("source_text")
        return LayoutResult(
            pdf=pdf_path,
            qa_report=_report(passed=True),
            layout_options=kwargs.get("base_options", {}),
            attempts_count=1,
            selected_variant="base",
        )

    monkeypatch.setattr(worker_main.settings, "tmp_dir", str(tmp_path))
    monkeypatch.setattr(worker_main, "download_source", lambda job, workdir: pdf_path)
    monkeypatch.setattr(worker_main, "extract_pdf_text", lambda source: raw_text)
    monkeypatch.setattr(worker_main, "build_whub_json", _build_whub_json)
    monkeypatch.setattr(worker_main, "assert_no_contact_in_json", lambda structured: None)
    monkeypatch.setattr(worker_main, "enforce_client_first_name", lambda structured, first_name: None)
    monkeypatch.setattr(worker_main, "render_pdf", lambda *args, **kwargs: pdf_path)
    monkeypatch.setattr(worker_main, "run_qa", Mock(return_value=_report(passed=True)))
    monkeypatch.setattr(worker_main, "run_layout", _mock_run_layout)
    monkeypatch.setattr(worker_main, "forbidden_candidate_name_parts", _forbidden)
    monkeypatch.setattr(worker_main, "save_version", lambda *args, **kwargs: {"id": "version-1", "version_number": 1})
    monkeypatch.setattr(
        worker_main,
        "emit_event",
        lambda request_id, event, payload=None: events.append((event, payload or {})),
    )

    class _CommentsTable:
        def select(self, *_args): return self
        def update(self, *_args, **_kwargs): return self
        def eq(self, *_args): return self
        def execute(self): return type("Res", (), {"data": []})()

    monkeypatch.setattr(worker_main.client, "table", lambda table: _CommentsTable())

    worker_main.process_job({"id": "request-1", "candidate_first_name": "Jean", "instructions": ""})

    sanitized_text = captured["structured_text"]
    for raw_value in ("jean@example.com", "06 12 34 56 78", "linkedin.com/in/jean", "CV téléchargé depuis Hellowork"):
        assert raw_value not in sanitized_text
    assert "Compétences: Python" in sanitized_text
    assert "Expériences: architecte cloud" in sanitized_text
    assert captured["layout_source_text"] == sanitized_text
    assert captured["forbidden_args"] == ("Jean", raw_text)

    source_sanitized_events = [payload for event, payload in events if event == "source_sanitized"]
    assert len(source_sanitized_events) == 1
    payload = source_sanitized_events[0]
    assert payload["removed_email_count"] == 1
    assert payload["removed_phone_count"] == 1
    assert payload["removed_linkedin_count"] == 1
    assert payload["removed_hellowork_line_count"] == 1
    payload_repr = repr(payload)
    for raw_value in ("jean@example.com", "06 12 34 56 78", "linkedin.com/in/jean", "CV téléchargé depuis Hellowork"):
        assert raw_value not in payload_repr


def test_process_job_infers_first_name_when_portal_omits_it(monkeypatch, tmp_path):
    hodard_source = "\n".join(
        [f"Skill line {i}: Python, Kubernetes, Terraform, AWS" for i in range(1, 47)]
        + ["FLORIAN HODARD", "INGÉNIEUR DEVOPS SENIOR"]
    )
    captured = {}
    events = []
    saved = {}
    pdf_path = tmp_path / "output.pdf"
    pdf_path.write_bytes(b"%PDF result")

    def _build_whub_json(text, instructions, comments, candidate_first_name):
        captured["candidate_first_name"] = candidate_first_name
        return {"name": "FLORIAN HODARD", "formations": [], "skills": [], "experiences": []}

    def _enforce_client_first_name(structured, first_name):
        captured["enforced_first_name"] = first_name

    def _forbidden(candidate_first_name, source_text=None):
        captured["forbidden_args"] = (candidate_first_name, source_text)
        return []

    def _mock_run_layout(**kwargs):
        return LayoutResult(
            pdf=pdf_path,
            qa_report=_report(passed=True),
            layout_options=kwargs.get("base_options", {}),
            attempts_count=1,
            selected_variant="base",
        )

    monkeypatch.setattr(worker_main.settings, "tmp_dir", str(tmp_path))
    monkeypatch.setattr(worker_main, "download_source", lambda job, workdir: pdf_path)
    monkeypatch.setattr(worker_main, "extract_pdf_text", lambda source: hodard_source)
    monkeypatch.setattr(worker_main, "build_whub_json", _build_whub_json)
    monkeypatch.setattr(worker_main, "assert_no_contact_in_json", lambda structured: None)
    monkeypatch.setattr(worker_main, "enforce_client_first_name", _enforce_client_first_name)
    monkeypatch.setattr(worker_main, "render_pdf", lambda *args, **kwargs: pdf_path)
    monkeypatch.setattr(worker_main, "run_qa", Mock(return_value=_report(passed=True)))
    monkeypatch.setattr(worker_main, "run_layout", _mock_run_layout)
    monkeypatch.setattr(worker_main, "forbidden_candidate_name_parts", _forbidden)
    monkeypatch.setattr(
        worker_main, "save_version",
        lambda *args, **kwargs: saved.update({"args": args, "kwargs": kwargs}) or {"id": "version-1", "version_number": 1},
    )
    monkeypatch.setattr(
        worker_main, "emit_event",
        lambda request_id, event, payload=None: events.append((event, payload or {})),
    )

    class _CommentsTable:
        def select(self, *_args): return self
        def update(self, *_args, **_kwargs): return self
        def eq(self, *_args): return self
        def execute(self): return type("Res", (), {"data": []})()

    monkeypatch.setattr(worker_main.client, "table", lambda table: _CommentsTable())

    worker_main.process_job({"id": "request-1", "candidate_first_name": "", "instructions": ""})

    assert captured.get("candidate_first_name") == "FLORIAN", (
        f"Expected build_whub_json candidate_first_name=FLORIAN, got {captured.get('candidate_first_name')}"
    )
    assert captured.get("enforced_first_name") == "FLORIAN", (
        f"Expected enforce_client_first_name first_name=FLORIAN, got {captured.get('enforced_first_name')}"
    )
    assert saved["kwargs"]["request_status"] == "ready", (
        f"Expected status=ready, got {saved['kwargs']['request_status']}"
    )
