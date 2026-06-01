from pathlib import Path
from unittest.mock import Mock

from src.layout_variants import (
    LayoutVariantAttempt,
    run_bounded_layout_variant_loop,
    select_best_layout_variant,
)
from src.qa import QAError


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
        "human_taste": {"score": 80, "verdict": "acceptable"},
    }
    report.update(overrides)
    return report


def _attempt(name, score, status="draft", **report_overrides):
    report = _report(human_taste={"score": score, "verdict": status}, **report_overrides)
    return LayoutVariantAttempt(
        name=name,
        pdf=Path(f"/tmp/{name}.pdf"),
        qa_report=report,
        status=status,
        layout_options={"variant": name},
    )


def test_selector_chooses_best_human_taste_score():
    weaker = _attempt("base", 72, layout_issues=[{"code": "page_too_dense"}])
    better = _attempt("layout_retry", 91, status="passed", passed=True, layout_issues=[])

    selection = select_best_layout_variant([weaker, better])

    assert selection.selected == better
    assert selection.selected_pdf == better.pdf
    assert selection.hard_failure is None


def test_selector_never_selects_hard_blocker_even_with_high_score():
    hard = _attempt("contact_leak", 100, status="failed", contact_hits=["email"])
    safe = _attempt("safe_draft", 70, status="draft", layout_issues=[{"code": "last_page_sparse"}])

    selection = select_best_layout_variant([hard, safe])

    assert selection.selected == safe
    assert selection.hard_failure is None


def test_selector_returns_hard_failure_when_all_variants_are_failed():
    hard = _attempt("base", 100, status="failed", contact_hits=["email"])

    selection = select_best_layout_variant([hard])

    assert selection.selected is None
    assert selection.hard_failure == hard


def test_bounded_loop_retries_once_and_selects_improved_variant(tmp_path):
    pdfs = []

    def fake_render(_structured, _workdir, layout_options=None, output_name="output.pdf"):
        pdf = tmp_path / output_name
        pdf.write_bytes(b"%PDF")
        pdfs.append((pdf, layout_options))
        return pdf

    first_report = _report(
        layout_issues=[{"code": "last_page_sparse", "page": 2}],
        human_taste={"score": 66, "verdict": "poor"},
    )
    second_report = _report(passed=True, layout_issues=[], human_taste={"score": 92, "verdict": "good"})
    fake_run_qa = Mock(side_effect=[QAError(first_report), second_report])

    selection = run_bounded_layout_variant_loop(
        structured={"name": "ZAHIA", "formations": [], "skills": [], "experiences": []},
        workdir=tmp_path,
        base_options={"force_experiences_new_page": True, "force_page_break_before_experience_indexes": [1]},
        render_pdf=fake_render,
        run_qa=fake_run_qa,
        max_attempts=2,
    )

    assert len(selection.attempts) == 2
    assert len(pdfs) == 2
    assert selection.selected is not None
    assert selection.selected.name == "layout_retry"
    assert selection.selected.layout_options["force_experiences_new_page"] is False
    assert selection.selected.layout_options["force_page_break_before_experience_indexes"] == []


def test_bounded_loop_does_not_retry_hard_blockers(tmp_path):
    def fake_render(_structured, _workdir, layout_options=None, output_name="output.pdf"):
        pdf = tmp_path / output_name
        pdf.write_bytes(b"%PDF")
        return pdf

    hard_report = _report(contact_hits=["email"], layout_issues=[{"code": "page_too_dense"}])
    fake_run_qa = Mock(side_effect=[QAError(hard_report)])

    selection = run_bounded_layout_variant_loop(
        structured={"name": "ZAHIA", "formations": [], "skills": [], "experiences": []},
        workdir=tmp_path,
        base_options={"anti_crowding": True},
        render_pdf=fake_render,
        run_qa=fake_run_qa,
        max_attempts=2,
    )

    assert len(selection.attempts) == 1
    assert selection.selected is None
    assert selection.hard_failure is not None
    assert fake_run_qa.call_count == 1
