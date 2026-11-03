from pathlib import Path

from src import main as worker_main
from src.visual_skills_extraction import VisualSkillsResult


def test_apply_source_wins_post_structuring_replaces_skills(monkeypatch, tmp_path: Path):
    source = tmp_path / "source.pdf"
    source.write_bytes(b"fake")

    monkeypatch.setattr(
        worker_main,
        "extract_visual_skills",
        lambda path: VisualSkillsResult(
            skills=[{"category": "Mainframe", "items": ["COBOL"]}],
            confidence=0.9,
            warnings=[],
        ),
    )

    structured = {"skills": [{"category": "Backend", "items": ["bad"]}]}

    result = worker_main._apply_source_wins_post_structuring(structured, source)

    assert result["skills"] == [{"category": "Mainframe", "items": ["COBOL"]}]
    assert result["_source_overrides"]["skills"]["source"] == "visual_pdf_blocks"


def test_apply_source_wins_post_structuring_keeps_skills_on_low_confidence(monkeypatch, tmp_path: Path):
    source = tmp_path / "source.pdf"
    source.write_bytes(b"fake")

    monkeypatch.setattr(
        worker_main,
        "extract_visual_skills",
        lambda path: VisualSkillsResult(skills=[], confidence=0.4, warnings=["too_few_visual_skills"]),
    )

    structured = {"skills": [{"category": "Backend", "items": ["Java"]}]}

    result = worker_main._apply_source_wins_post_structuring(structured, source)

    assert result["skills"] == [{"category": "Backend", "items": ["Java"]}]
    assert "_source_overrides" not in result


def _run_content_job(monkeypatch, tmp_path: Path, comment_body: str) -> list:
    """Run process_job on a content revision and return the override calls."""
    from unittest.mock import Mock

    from src.layout import LayoutResult

    pdf_path = tmp_path / "out.pdf"
    pdf_path.write_bytes(b"%PDF")
    report = {"passed": True, "pages": 1, "contact_hits": [], "bad_glyphs": False, "content_integrity_issues": [],
              "text_overflow_hits": [], "layout_issues": [], "has_logo": True, "has_watermark": True}
    override_calls: list = []
    source_text = "\n".join(["Jean Source", "Compétences: Python, Kubernetes, Terraform, Docker, Ansible."] * 12)

    monkeypatch.setattr(worker_main.settings, "tmp_dir", str(tmp_path))
    monkeypatch.setattr(worker_main, "download_source", lambda job, workdir: pdf_path)
    monkeypatch.setattr(worker_main, "extract_pdf_text", lambda source: source_text)
    monkeypatch.setattr(worker_main, "build_whub_json", lambda *a, **k: {"name": "JEAN", "formations": [], "skills": [], "experiences": []})
    monkeypatch.setattr(worker_main, "_apply_source_wins_post_structuring", lambda structured, source: override_calls.append(source) or structured)
    monkeypatch.setattr(worker_main, "assert_no_contact_in_json", lambda structured: None)
    monkeypatch.setattr(worker_main, "run_layout", lambda **kwargs: LayoutResult(
        pdf=pdf_path, qa_report=dict(report), layout_options={}, attempts_count=1, selected_variant="base"))
    monkeypatch.setattr(worker_main, "save_version", lambda *a, **k: {"id": "v2", "version_number": 2})
    monkeypatch.setattr(worker_main, "emit_event", Mock())

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
                return type("Res", (), {"data": [{"body": comment_body, "comment_type": "revision"}]})()
            return type("Res", (), {"data": []})()

    monkeypatch.setattr(worker_main.client, "table", lambda table: _FakeTable(table))
    worker_main.process_job({"id": "request-1", "current_version_id": None, "candidate_first_name": "Jean", "instructions": ""})
    return override_calls


def test_skills_revision_comment_skips_visual_skills_override(monkeypatch, tmp_path: Path):
    calls = _run_content_job(monkeypatch, tmp_path, "Dans Compétences, supprime la catégorie Projets.")

    assert calls == []


def test_other_content_revision_keeps_visual_skills_override(monkeypatch, tmp_path: Path):
    calls = _run_content_job(monkeypatch, tmp_path, "Ajoute la mission manquante chez ACME.")

    assert len(calls) == 1
