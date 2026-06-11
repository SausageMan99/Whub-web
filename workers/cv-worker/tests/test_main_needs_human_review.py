"""Tests for ``process_job`` routing when source extraction is too uncertain.

The router must:
- Build a source profile via ``_build_source_quality_payload``.
- Decide whether the request needs human review using the shared helper.
- When human review is required: set status=``needs_human_review`` on the
  ``cv_requests`` row, emit a ``needs_human_review`` event, and return
  without ever calling ``build_whub_json`` or the model.
- When human review is NOT required: continue the normal pipeline and
  reach ``save_version`` (or any other downstream step) as before.
"""
from __future__ import annotations

import pytest

from src import main as worker_main


class _TracingClient:
    """Minimal Supabase fake that records table operations and update payloads."""

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


def test_process_job_short_text_routes_to_needs_human_review(
    tracing_client, monkeypatch, tmp_path
):
    """Tiny / scanned source must short-circuit to needs_human_review."""
    captured: dict = {}
    events: list = []
    pdf_path = tmp_path / "src.pdf"
    pdf_path.write_bytes(b"%PDF x")

    monkeypatch.setattr(worker_main.settings, "tmp_dir", str(tmp_path))
    monkeypatch.setattr(worker_main, "download_source", lambda job, workdir: pdf_path)
    monkeypatch.setattr(
        worker_main,
        "extract_pdf_text",
        lambda source: "CV\nCourt\n2024 Stage\n",
    )
    monkeypatch.setattr(
        worker_main,
        "emit_event",
        lambda rid, event, payload=None: events.append((rid, event, payload or {})),
    )
    monkeypatch.setattr(
        worker_main,
        "build_whub_json",
        lambda *a, **kw: (
            captured.setdefault("build_called", True),
            {"name": "X"},
        )[1],
    )
    monkeypatch.setattr(
        worker_main,
        "save_version",
        lambda *a, **kw: (captured.setdefault("save_called", True), {"id": "v1", "version_number": 1})[1],
    )

    worker_main.process_job(
        {"id": "req-1", "candidate_first_name": "ZAHIA", "instructions": ""}
    )

    # No model call, no save.
    assert "build_called" not in captured
    assert "save_called" not in captured

    # The cv_requests row must have been updated to needs_human_review.
    cv_requests_updates = [
        op for op in tracing_client.operations if op["table"] == "cv_requests"
    ]
    assert cv_requests_updates, "expected at least one cv_requests update"
    last = cv_requests_updates[-1]
    assert last["payload"]["status"] == "needs_human_review"
    assert isinstance(last["payload"]["last_error"], str)
    assert "humaine" in last["payload"]["last_error"].lower() or "prénom" in last["payload"]["last_error"].lower()

    # A needs_human_review event must have been emitted.
    assert any(ev[1] == "needs_human_review" for ev in events)


def test_process_job_normal_source_does_not_route_to_human_review(
    tracing_client, monkeypatch, tmp_path
):
    """A well-formed CV must continue past the source profile step."""
    captured: dict = {}
    pdf_path = tmp_path / "src.pdf"
    pdf_path.write_bytes(b"%PDF x")

    monkeypatch.setattr(worker_main.settings, "tmp_dir", str(tmp_path))
    monkeypatch.setattr(worker_main, "download_source", lambda job, workdir: pdf_path)
    monkeypatch.setattr(
        worker_main,
        "extract_pdf_text",
        lambda source: (
            "Prénom NOM\n"
            "Architecte solution cloud et devops senior\n"
            "Compétences: Python, Kubernetes, Terraform, AWS, GCP, Azure, Docker, Helm\n"
            "Expériences: pilotage de projets data et industrialisation de plateformes internes.\n"
            "Réalisations: migration applicative, automatisation CI/CD, sécurisation des déploiements.\n"
            "Formation: école d'ingénieur, certifications cloud, ateliers agiles et mentorat technique.\n"
            "Langues: français, anglais professionnel, communication avec équipes produit et métier.\n"
        ),
    )
    monkeypatch.setattr(
        worker_main,
        "build_whub_json",
        lambda *a, **kw: (
            captured.setdefault("built", True),
            {
                "name": "PRÉNOM",
                "formations": [],
                "skills": [],
                "experiences": [],
            },
        )[1],
    )
    monkeypatch.setattr(worker_main, "assert_no_contact_in_json", lambda s: None)
    monkeypatch.setattr(worker_main, "enforce_client_first_name", lambda s, n: None)
    monkeypatch.setattr(worker_main, "render_pdf", lambda *a, **kw: pdf_path)
    monkeypatch.setattr(
        worker_main,
        "run_qa",
        lambda *a, **kw: {
            "pages": 1,
            "has_logo": True,
            "has_watermark": True,
            "layout_issues": [],
        },
    )
    monkeypatch.setattr(
        worker_main,
        "save_version",
        lambda *a, **kw: (captured.setdefault("saved", True), {"id": "v1", "version_number": 1})[1],
    )
    monkeypatch.setattr(worker_main, "emit_event", lambda *a, **kw: None)

    worker_main.process_job(
        {"id": "req-3", "candidate_first_name": "Prénom", "instructions": ""}
    )

    assert captured.get("built") is True
    assert captured.get("saved") is True
    # No needs_human_review status update on a healthy source.
    cv_requests_updates = [
        op for op in tracing_client.operations if op["table"] == "cv_requests"
    ]
    for op in cv_requests_updates:
        assert op["payload"].get("status") != "needs_human_review"
