"""Tests for ``process_job`` shadow evaluation of the content-preserving pipeline.

Shadow mode must:
- Never change the delivered output, never update ``current_version_id``.
- Always emit a redacted ``content_preserving_shadow_evaluated`` event.
- Coexist with the existing pipeline (``build_whub_json`` + ``save_version``).
- Be a no-op when the flag is off.
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
    """Return the input text unchanged from sanitization so tests focus on the shadow hook."""
    monkeypatch.setattr(
        worker_main,
        "sanitize_source_text",
        lambda text, first_name: type("Sanitization", (), {"text": text, "report": {}})(),
    )


def _patch_source_profile(monkeypatch):
    """Force the source profile to 'normal' so the pipeline does not short-circuit to needs_human_review."""
    monkeypatch.setattr(worker_main, "classify_source_profile", lambda text: {"profile": "normal", "chars": len(text), "line_count": text.count("\n") + 1})
    monkeypatch.setattr(worker_main, "should_require_human_review", lambda profile: False)
    monkeypatch.setattr(worker_main, "_build_source_quality_payload", lambda text, raw_chars, sanitized_chars: {
        "source_profile": "normal",
        "scores": {"extraction": 80, "fidelity": 0, "layout": 0, "overall": 80},
        "metrics": {"raw_chars": raw_chars, "sanitized_chars": sanitized_chars, "line_count": text.count("\n") + 1, "mission_markers": 1, "ats_markers": 0, "short_line_ratio": 0.1},
        "hard_blockers": [],
        "soft_warnings": [],
    })


def _patch_existing_pipeline(monkeypatch, captured, pdf_path, events, tracer_ops):
    """Wire the existing pipeline to record calls and produce a fake version."""
    monkeypatch.setattr(worker_main, "build_whub_json", lambda *a, **kw: (captured.setdefault("built", True), {"name": "PRÉNOM", "formations": [], "skills": [], "experiences": []})[1])
    monkeypatch.setattr(worker_main, "assert_no_contact_in_json", lambda s: None)
    monkeypatch.setattr(worker_main, "enforce_client_first_name", lambda s, n: None)
    monkeypatch.setattr(worker_main, "render_pdf", lambda *a, **kw: pdf_path)
    monkeypatch.setattr(worker_main, "run_qa", lambda *a, **kw: {"pages": 1, "has_logo": True, "has_watermark": True, "layout_issues": []})
    monkeypatch.setattr(worker_main, "save_version", lambda *a, **kw: (captured.setdefault("saved", True), {"id": "v1", "version_number": 1})[1])
    monkeypatch.setattr(worker_main, "build_layout_packing_options", lambda s: {})
    monkeypatch.setattr(worker_main, "run_layout", lambda **kw: type("LayoutResult", (), {"pdf": pdf_path, "qa_report": kw.get("base_options", {}), "attempts_count": 1, "selected_variant": "natural"})())
    monkeypatch.setattr(worker_main, "forbidden_candidate_name_parts", lambda *a, **kw: [])
    monkeypatch.setattr(worker_main, "_infer_first_name_from_source", lambda *a, **kw: ("", []))
    monkeypatch.setattr(worker_main, "_attach_final_quality_report", lambda **kw: kw["qa_report"])
    monkeypatch.setattr(worker_main, "classify_qa_report", lambda qa: ("passed", []))
    monkeypatch.setattr(worker_main, "emit_event", lambda rid, ev, payload=None: events.append((rid, ev, payload or {})))


def test_process_job_shadow_off_emits_no_shadow_event(tracing_client, monkeypatch, tmp_path, normal_cv_text):
    captured: dict = {}
    events: list = []
    pdf_path = tmp_path / "src.pdf"
    pdf_path.write_bytes(b"%PDF x")
    monkeypatch.setattr(worker_main.settings, "tmp_dir", str(tmp_path))
    monkeypatch.setattr(worker_main.settings, "whub_content_preserving_shadow", False)
    monkeypatch.setattr(worker_main, "download_source", lambda job, workdir: pdf_path)
    monkeypatch.setattr(worker_main, "extract_pdf_text", lambda source: normal_cv_text)
    _patch_sanitize(monkeypatch, normal_cv_text)
    _patch_source_profile(monkeypatch)
    _patch_existing_pipeline(monkeypatch, captured, pdf_path, events, tracing_client.operations)

    worker_main.process_job({"id": "req-shadow-off", "candidate_first_name": "Prénom", "instructions": ""})

    assert captured.get("built") is True
    assert captured.get("saved") is True
    assert not any(ev[1] == "content_preserving_shadow_evaluated" for ev in events)
    assert not any(ev[1] == "content_preserving_shadow_failed" for ev in events)


def test_process_job_shadow_on_emits_shadow_event_and_keeps_existing_output(tracing_client, monkeypatch, tmp_path, normal_cv_text):
    captured: dict = {}
    events: list = []
    pdf_path = tmp_path / "src.pdf"
    pdf_path.write_bytes(b"%PDF x")
    monkeypatch.setattr(worker_main.settings, "tmp_dir", str(tmp_path))
    monkeypatch.setattr(worker_main.settings, "whub_content_preserving_shadow", True)
    monkeypatch.setattr(worker_main, "download_source", lambda job, workdir: pdf_path)
    monkeypatch.setattr(worker_main, "extract_pdf_text", lambda source: normal_cv_text)
    _patch_sanitize(monkeypatch, normal_cv_text)
    _patch_source_profile(monkeypatch)
    _patch_existing_pipeline(monkeypatch, captured, pdf_path, events, tracing_client.operations)

    worker_main.process_job({"id": "req-shadow-on", "candidate_first_name": "Prénom", "instructions": ""})

    # Existing pipeline still ran and saved a version.
    assert captured.get("built") is True
    assert captured.get("saved") is True

    # Shadow event emitted.
    shadow_events = [ev for ev in events if ev[1] == "content_preserving_shadow_evaluated"]
    assert len(shadow_events) == 1
    payload = shadow_events[0][2]
    assert "variant" in payload
    assert "missing_required_blocks_count" in payload
    assert isinstance(payload["missing_required_blocks_count"], int)
    assert payload["missing_required_blocks_count"] >= 0
    # No raw contact data should leak in the event.
    dumped = str(payload)
    assert "@" not in dumped
    assert "linkedin.com" not in dumped

    # No current_version_id update was made by the shadow path (it does not
    # touch the cv_versions row at all).
    version_ops = [op for op in tracing_client.operations if op["table"] == "cv_versions"]
    assert not version_ops
