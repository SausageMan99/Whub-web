"""Tests for ``process_job`` active content-preserving pipeline branch.

When ``whub_content_preserving_pipeline=True``, the new pipeline must own
the rest of the job: ``build_whub_json`` must NOT be called, and
``save_version`` MUST be called with a content-preserving PDF. When the
flag is off, the existing pipeline must run normally.
"""
from __future__ import annotations

import pytest

from src import main as worker_main


class _TracingClient:
    """Minimal Supabase fake that records table operations."""

    def __init__(self):
        self.operations: list[dict] = []

    def table(self, name: str):
        outer = self

        class _Table:
            def __init__(self):
                self._name = name
                self._payload = None

            def select(self, *_args, **_kwargs):
                return self

            def update(self, payload):
                self._payload = payload
                return self

            def insert(self, payload):
                self._payload = payload
                return self

            def eq(self, *_args, **_kwargs):
                return self

            def execute(self):
                outer.operations.append({"table": self._name, "payload": self._payload})
                return type("Res", (), {"data": []})()

        return _Table()


@pytest.fixture
def tracing_client(monkeypatch):
    client = _TracingClient()
    monkeypatch.setattr(worker_main, "client", client)
    return client


@pytest.fixture
def normal_cv_text():
    return (
        "Prénom NOM\n"
        "Architecte solution cloud et devops senior\n\n"
        "Compétences: Python, Kubernetes, Terraform, AWS, GCP, Azure, Docker, Helm\n\n"
        "Expériences: pilotage de projets data et industrialisation de plateformes internes.\n\n"
        "Formation: école d'ingénieur, certifications cloud, ateliers agiles et mentorat technique.\n\n"
        "Langues: français, anglais professionnel, communication avec équipes produit et métier.\n"
    )


def _patch_sanitize(monkeypatch, sanitized_text):
    monkeypatch.setattr(
        worker_main,
        "sanitize_source_text",
        lambda text, first_name: type("Sanitization", (), {"text": text, "report": {}})(),
    )


def _patch_source_profile(monkeypatch):
    monkeypatch.setattr(worker_main, "classify_source_profile", lambda text: {"profile": "normal", "chars": len(text), "line_count": text.count("\n") + 1})
    monkeypatch.setattr(worker_main, "should_require_human_review", lambda profile: False)
    monkeypatch.setattr(worker_main, "_build_source_quality_payload", lambda text, raw_chars, sanitized_chars: {
        "source_profile": "normal",
        "scores": {"extraction": 80, "fidelity": 0, "layout": 0, "overall": 80},
        "metrics": {"raw_chars": raw_chars, "sanitized_chars": sanitized_chars, "line_count": text.count("\n") + 1, "mission_markers": 1, "ats_markers": 0, "short_line_ratio": 0.1},
        "hard_blockers": [],
        "soft_warnings": [],
    })


def _patch_existing_pipeline(monkeypatch, captured, pdf_path, events, tracing_client):
    monkeypatch.setattr(worker_main, "build_whub_json", lambda *a, **kw: (captured.setdefault("built", True), {"name": "PRÉNOM", "formations": [], "skills": [], "experiences": []})[1])
    monkeypatch.setattr(worker_main, "assert_no_contact_in_json", lambda s: None)
    monkeypatch.setattr(worker_main, "enforce_client_first_name", lambda s, n: None)
    monkeypatch.setattr(worker_main, "render_pdf", lambda *a, **kw: pdf_path)
    monkeypatch.setattr(worker_main, "run_qa", lambda *a, **kw: {"pages": 1, "has_logo": True, "has_watermark": True, "layout_issues": []})
    monkeypatch.setattr(worker_main, "build_layout_packing_options", lambda s: {})
    monkeypatch.setattr(worker_main, "run_layout", lambda **kw: type("LayoutResult", (), {"pdf": pdf_path, "qa_report": kw.get("base_options", {}), "attempts_count": 1, "selected_variant": "natural"})())
    monkeypatch.setattr(worker_main, "forbidden_candidate_name_parts", lambda *a, **kw: [])
    monkeypatch.setattr(worker_main, "_infer_first_name_from_source", lambda *a, **kw: ("", []))
    monkeypatch.setattr(worker_main, "_attach_final_quality_report", lambda **kw: kw["qa_report"])
    monkeypatch.setattr(worker_main, "classify_qa_report", lambda qa: ("passed", []))
    # Let the real save_version run so the client mock records cv_versions operations.
    # Stub the storage uploads so the test doesn't need real Supabase storage.
    from src import storage as worker_storage
    monkeypatch.setattr(worker_storage, "client", tracing_client)
    monkeypatch.setattr(worker_storage, "upload_bytes", lambda *a, **kw: "stub")
    monkeypatch.setattr(worker_main, "emit_event", lambda rid, ev, payload=None: events.append((rid, ev, payload or {})))


def test_process_job_active_pipeline_skips_existing_pipeline(tracing_client, monkeypatch, tmp_path, normal_cv_text):
    captured: dict = {}
    events: list = []
    pdf_path = tmp_path / "src.pdf"
    pdf_path.write_bytes(b"%PDF x")
    monkeypatch.setattr(worker_main.settings, "tmp_dir", str(tmp_path))
    monkeypatch.setattr(worker_main.settings, "whub_content_preserving_pipeline", True)
    monkeypatch.setattr(worker_main.settings, "whub_content_preserving_shadow", False)
    monkeypatch.setattr(worker_main, "download_source", lambda job, workdir: pdf_path)
    monkeypatch.setattr(worker_main, "extract_pdf_text", lambda source: normal_cv_text)
    _patch_sanitize(monkeypatch, normal_cv_text)
    _patch_source_profile(monkeypatch)
    _patch_existing_pipeline(monkeypatch, captured, pdf_path, events, tracing_client)

    # The active pipeline calls save_version itself, but it needs a stub because
    # the real save_version does storage uploads. Mock it so the test stays
    # pure but still record the structured_json payload for assertions.
    saved_structured_holder: dict = {}
    saved_qa_holder: dict = {}
    saved_request_status_holder: dict = {}
    saved_qa_status_holder: dict = {}

    def fake_save_version(request_id, structured_json, pdf_path, qa_report, *, request_status, qa_status, owner):
        saved_structured_holder["value"] = structured_json
        saved_qa_holder["value"] = qa_report
        saved_request_status_holder["value"] = request_status
        saved_qa_status_holder["value"] = qa_status
        return {"id": "v1", "version_number": 1}

    monkeypatch.setattr(worker_main, "save_version", fake_save_version)

    # The active pipeline also persists structured_json via cv_versions insert.
    # Mirror that into the tracing_client.operations. We use a small wrapper
    # so cv_versions insert calls are recorded even when the test's
    # ``save_version`` mock bypasses the real function.
    original_table = tracing_client.table

    def recording_table(name):
        tbl = original_table(name)
        if name == "cv_versions":
            original_insert = tbl.insert

            def recording_insert(payload):
                tracing_client.operations.append({"table": "cv_versions", "payload": payload})
                return original_insert(payload)

            tbl.insert = recording_insert
        return tbl

    tracing_client.table = recording_table  # type: ignore[assignment]

    worker_main.process_job({"id": "req-active", "candidate_first_name": "Prénom", "instructions": ""})

    # Existing pipeline was NOT called.
    assert "built" not in captured, "build_whub_json must not be called when active pipeline is on"

    # save_version was called by the active pipeline with a content-preserving structured_json.
    assert "value" in saved_structured_holder
    saved_structured = saved_structured_holder["value"]
    assert saved_structured["content_preserving"]["variant"] in {
        "deterministic_content_preserving",
        "compact_content_preserving",
        "experience_first_content_preserving",
    }
    assert saved_structured["content_preserving"]["missing_required_blocks"] == []
    assert saved_qa_holder["value"].get("content_preserving") is True
    assert saved_request_status_holder["value"] == "ready"
    assert saved_qa_status_holder["value"] == "passed"

    # ready event was emitted with a layout_variant.
    ready_events = [ev for ev in events if ev[1] in {"ready", "draft_ready"}]
    assert ready_events
    assert "layout_variant" in ready_events[0][2]
    assert "version_id" in ready_events[0][2]

    # ready event was emitted with a layout_variant.
    ready_events = [ev for ev in events if ev[1] in {"ready", "draft_ready"}]
    assert ready_events
    assert "layout_variant" in ready_events[0][2]
    assert "version_id" in ready_events[0][2]

def test_process_job_active_off_runs_existing_pipeline(tracing_client, monkeypatch, tmp_path, normal_cv_text):
    captured: dict = {}
    events: list = []
    pdf_path = tmp_path / "src.pdf"
    pdf_path.write_bytes(b"%PDF x")
    monkeypatch.setattr(worker_main.settings, "tmp_dir", str(tmp_path))
    monkeypatch.setattr(worker_main.settings, "whub_content_preserving_pipeline", False)
    monkeypatch.setattr(worker_main.settings, "whub_content_preserving_shadow", False)
    monkeypatch.setattr(worker_main, "download_source", lambda job, workdir: pdf_path)
    monkeypatch.setattr(worker_main, "extract_pdf_text", lambda source: normal_cv_text)
    _patch_sanitize(monkeypatch, normal_cv_text)
    _patch_source_profile(monkeypatch)
    _patch_existing_pipeline(monkeypatch, captured, pdf_path, events, tracing_client)

    # Mock save_version to record its structured_json (existing pipeline, no
    # content_preserving payload). Bypasses real save_version which needs
    # real Supabase + storage.
    saved_structured_holder: dict = {}

    def fake_save_version(request_id, structured_json, pdf_path, qa_report, *, request_status, qa_status, owner):
        saved_structured_holder["value"] = structured_json
        return {"id": "v1", "version_number": 1}

    monkeypatch.setattr(worker_main, "save_version", fake_save_version)

    worker_main.process_job({"id": "req-active-off", "candidate_first_name": "Prénom", "instructions": ""})

    # Existing pipeline was called.
    assert captured.get("built") is True
    assert "value" in saved_structured_holder
    # No content_preserving key in the structured_json from the existing pipeline.
    assert "content_preserving" not in saved_structured_holder["value"]

