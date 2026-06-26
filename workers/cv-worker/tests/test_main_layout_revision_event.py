from __future__ import annotations

from copy import deepcopy
from unittest.mock import Mock

import pytest

from src import main as worker_main
from src.layout import LayoutResult


_MINIMAL_CV_SOURCE = "\n".join(
    [
        "Philippe Source",
        "Compétences: Python, Kubernetes, Terraform, conduite du changement, architecture cloud.",
        "Expériences: pilotage de projets data et industrialisation de plateformes internes.",
        "Réalisations: migration applicative, automatisation CI/CD, sécurisation des déploiements.",
        "Formation: école d'ingénieur, certifications cloud, ateliers agiles et mentorat technique.",
        "Langues: français, anglais professionnel, communication avec équipes produit et métier.",
        "Objectif: Ingénieur DevOps senior.",
        "Projets: refonte plateforme data, optimisation coûts cloud, gouvernance DevOps.",
        "Outils: Docker, Terraform, Ansible, Prometheus, Grafana.",
        "Méthodologies: Agile, Scrum, SAFe, ITIL.",
        "Soft skills: leadership, communication, esprit d'équipe.",
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


PHILIPPE_CV_FIXTURE = {
    "name": "PHILIPPE",
    "title": "Ingénieur DevOps",
    "formations": [{"date": "2010", "degree": "Master", "school": "École d'ingénieur"}],
    "skills": [
        {"category": "Dev", "items": ["Python", "Kubernetes"]},
    ],
    "experiences": [
        {
            "date": "2020 – 2023",
            "role": "Ingénieur DevOps",
            "company_highlight": "Client",
            "sections": [
                {
                    "heading": "Missions clés",
                    "content": [
                        "Migration applicative",
                        "Automatisation CI/CD",
                    ],
                }
            ],
        }
    ],
}


def test_layout_revision_emits_event_with_intent_metadata(monkeypatch, tmp_path):
    events = []

    pdf_path = tmp_path / "layout.pdf"
    pdf_path.write_bytes(b"%PDF layout")

    monkeypatch.setattr(worker_main.settings, "tmp_dir", str(tmp_path))
    monkeypatch.setattr(worker_main.settings, "worker_name", "whub-cv-worker-hermes-local")
    monkeypatch.setattr(worker_main, "download_source", lambda job, workdir: pdf_path)
    monkeypatch.setattr(worker_main, "extract_pdf_text", lambda source: _MINIMAL_CV_SOURCE)
    monkeypatch.setattr(
        worker_main,
        "build_whub_json",
        Mock(side_effect=AssertionError("build_whub_json should not be called for layout_only revision")),
    )
    monkeypatch.setattr(worker_main, "assert_no_contact_in_json", lambda structured: None)
    monkeypatch.setattr(worker_main, "enforce_client_first_name", lambda structured, first_name: None)
    monkeypatch.setattr(worker_main, "render_pdf", lambda *args, **kwargs: pdf_path)
    monkeypatch.setattr(worker_main, "run_qa", Mock(return_value=_report()))
    monkeypatch.setattr(
        worker_main,
        "save_version",
        lambda *args, **kwargs: {"id": "version-2", "version_number": 2},
    )
    monkeypatch.setattr(
        worker_main,
        "emit_event",
        lambda request_id, event, payload=None: events.append((event, payload or {})),
    )

    def _mock_run_layout(**kwargs):
        return LayoutResult(
            pdf=pdf_path,
            qa_report=_report(),
            layout_options=kwargs.get("base_options", {}),
            attempts_count=1,
            selected_variant="base",
        )

    monkeypatch.setattr(worker_main, "run_layout", _mock_run_layout)

    class _FakeTable:
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
                return type(
                    "Res",
                    (),
                    {
                        "data": [
                            {
                                "body": "remonter la dernière mission clé de la derniere page sur page 3",
                                "comment_type": "revision",
                            }
                        ]
                    },
                )()
            if self.table == "cv_versions":
                return type(
                    "Res",
                    (),
                    {
                        "data": [
                            {
                                "version_number": 1,
                                "qa_status": "draft",
                                "qa_report": {
                                    "pages": 2,
                                    "layout_issues": [{"code": "last_page_sparse", "page": 2}],
                                },
                                "structured_json": PHILIPPE_CV_FIXTURE,
                            }
                        ]
                    },
                )()
            return type("Res", (), {"data": []})()

    monkeypatch.setattr(worker_main.client, "table", lambda table: _FakeTable(table))

    worker_main.process_job(
        {
            "id": "request-1",
            "current_version_id": "550e8400-e29b-41d4-a716-446655440000",
            "candidate_first_name": "PHILIPPE",
            "instructions": "",
        }
    )

    assert (
        "layout_revision_detected",
        {
            "intent": "layout_only",
            "comments_count": 1,
            "from_version_id": "550e8400-e29b-41d4-a716-446655440000",
            "routing": "renderer_only",
        },
    ) in events


def test_content_revision_does_not_emit_layout_revision_event(monkeypatch, tmp_path):
    events = []

    pdf_path = tmp_path / "content.pdf"
    pdf_path.write_bytes(b"%PDF content")

    monkeypatch.setattr(worker_main.settings, "tmp_dir", str(tmp_path))
    monkeypatch.setattr(worker_main.settings, "worker_name", "whub-cv-worker-hermes-local")
    monkeypatch.setattr(worker_main, "download_source", lambda job, workdir: pdf_path)
    monkeypatch.setattr(worker_main, "extract_pdf_text", lambda source: _MINIMAL_CV_SOURCE)
    monkeypatch.setattr(worker_main, "build_whub_json", lambda *args, **kwargs: {"name": "PHILIPPE", "formations": [], "skills": [], "experiences": []})
    monkeypatch.setattr(worker_main, "assert_no_contact_in_json", lambda structured: None)
    monkeypatch.setattr(worker_main, "enforce_client_first_name", lambda structured, first_name: None)
    monkeypatch.setattr(worker_main, "render_pdf", lambda *args, **kwargs: pdf_path)
    monkeypatch.setattr(worker_main, "run_qa", Mock(return_value=_report()))
    monkeypatch.setattr(
        worker_main,
        "save_version",
        lambda *args, **kwargs: {"id": "version-2", "version_number": 2},
    )
    monkeypatch.setattr(
        worker_main,
        "emit_event",
        lambda request_id, event, payload=None: events.append((event, payload or {})),
    )

    def _mock_run_layout(**kwargs):
        return LayoutResult(
            pdf=pdf_path,
            qa_report=_report(),
            layout_options=kwargs.get("base_options", {}),
            attempts_count=1,
            selected_variant="base",
        )

    monkeypatch.setattr(worker_main, "run_layout", _mock_run_layout)

    class _FakeTable:
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
                return type(
                    "Res",
                    (),
                    {
                        "data": [
                            {
                                "body": "ajouter l'expérience Thales",
                                "comment_type": "revision",
                            }
                        ]
                    },
                )()
            if self.table == "cv_versions":
                return type(
                    "Res",
                    (),
                    {
                        "data": [
                            {
                                "version_number": 1,
                                "qa_status": "draft",
                                "qa_report": {},
                                "structured_json": PHILIPPE_CV_FIXTURE,
                            }
                        ]
                    },
                )()
            return type("Res", (), {"data": []})()

    monkeypatch.setattr(worker_main.client, "table", lambda table: _FakeTable(table))

    worker_main.process_job(
        {
            "id": "request-2",
            "current_version_id": "550e8400-e29b-41d4-a716-446655440001",
            "candidate_first_name": "PHILIPPE",
            "instructions": "",
        }
    )

    assert not any(event == "layout_revision_detected" for event, _ in events)


def test_reset_revision_does_not_emit_layout_revision_event(monkeypatch, tmp_path):
    events = []

    pdf_path = tmp_path / "reset.pdf"
    pdf_path.write_bytes(b"%PDF reset")

    monkeypatch.setattr(worker_main.settings, "tmp_dir", str(tmp_path))
    monkeypatch.setattr(worker_main.settings, "worker_name", "whub-cv-worker-hermes-local")
    monkeypatch.setattr(worker_main, "download_source", lambda job, workdir: pdf_path)
    monkeypatch.setattr(worker_main, "extract_pdf_text", lambda source: _MINIMAL_CV_SOURCE)
    monkeypatch.setattr(worker_main, "build_whub_json", lambda *args, **kwargs: {"name": "PHILIPPE", "formations": [], "skills": [], "experiences": []})
    monkeypatch.setattr(worker_main, "assert_no_contact_in_json", lambda structured: None)
    monkeypatch.setattr(worker_main, "enforce_client_first_name", lambda structured, first_name: None)
    monkeypatch.setattr(worker_main, "render_pdf", lambda *args, **kwargs: pdf_path)
    monkeypatch.setattr(worker_main, "run_qa", Mock(return_value=_report()))
    monkeypatch.setattr(
        worker_main,
        "save_version",
        lambda *args, **kwargs: {"id": "version-3", "version_number": 3},
    )
    monkeypatch.setattr(
        worker_main,
        "emit_event",
        lambda request_id, event, payload=None: events.append((event, payload or {})),
    )

    def _mock_run_layout(**kwargs):
        return LayoutResult(
            pdf=pdf_path,
            qa_report=_report(),
            layout_options=kwargs.get("base_options", {}),
            attempts_count=1,
            selected_variant="base",
        )

    monkeypatch.setattr(worker_main, "run_layout", _mock_run_layout)

    class _FakeTable:
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
                return type(
                    "Res",
                    (),
                    {
                        "data": [
                            {
                                "body": "repartir de zéro",
                                "comment_type": "revision",
                            }
                        ]
                    },
                )()
            if self.table == "cv_versions":
                return type(
                    "Res",
                    (),
                    {
                        "data": [
                            {
                                "version_number": 1,
                                "qa_status": "draft",
                                "qa_report": {},
                                "structured_json": PHILIPPE_CV_FIXTURE,
                            }
                        ]
                    },
                )()
            return type("Res", (), {"data": []})()

    monkeypatch.setattr(worker_main.client, "table", lambda table: _FakeTable(table))

    worker_main.process_job(
        {
            "id": "request-3",
            "current_version_id": "550e8400-e29b-41d4-a716-446655440002",
            "candidate_first_name": "PHILIPPE",
            "instructions": "",
        }
    )

    assert not any(event == "layout_revision_detected" for event, _ in events)
