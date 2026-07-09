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
