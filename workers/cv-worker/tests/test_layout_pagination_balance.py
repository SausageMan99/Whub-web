"""Pagination fixes of 2026-11-03 (zahia / amina / noel / dense in the test bank)."""
from pathlib import Path

import fitz

from src.layout import run_layout
from src.layout.variants import LayoutVariantAttempt, select_best_layout_variant
from src.qa import find_layout_issues


def _codes(draw, tmp_path):
    doc = fitz.open()
    draw(doc)
    path = tmp_path / "qa.pdf"
    doc.save(str(path))
    return [issue["code"] for issue in find_layout_issues(fitz.open(str(path)))]


def test_skill_chunks_continued_on_page_one_are_not_an_overflow_page(tmp_path):
    def draw(doc):
        page = doc.new_page(width=595, height=842)
        page.insert_text((60, 300), "Stack technique (suite)", fontsize=8.3)
        page.insert_text((60, 312), "Docker · Kubernetes · Terraform", fontsize=7.8)
        page.insert_text((60, 420), "Expériences professionnelles", fontsize=13)
        doc.new_page(width=595, height=842).insert_text((60, 90), "• Pilotage du programme cloud.", fontsize=8)

    assert "skill_overflow_page_created" not in _codes(draw, tmp_path)


def test_experience_section_continued_next_to_tool_words_is_not_a_skill_overflow(tmp_path):
    # amina page 6: "Recette (suite)" then a line "Outils" further down.
    def draw(doc):
        doc.new_page(width=595, height=842).insert_text((60, 90), "Expériences professionnelles", fontsize=13)
        page = doc.new_page(width=595, height=842)
        page.insert_text((60, 82), "Recette (suite)", fontsize=8.4)
        page.insert_text((60, 95), "• Communication régulière sur l'avancement des tests.", fontsize=8)
        page.insert_text((60, 110), "Outils", fontsize=8.4)
        page.insert_text((60, 122), "• Mantis, Excel.", fontsize=8)

    assert "skill_overflow_page_created" not in _codes(draw, tmp_path)


def test_renderer_skills_continuation_page_is_still_detected(tmp_path):
    def draw(doc):
        doc.new_page(width=595, height=842).insert_text((60, 300), "Compétences techniques", fontsize=13)
        page = doc.new_page(width=595, height=842)
        page.insert_text((60, 82), " ".join("COMPÉTENCES TECHNIQUES (SUITE)"), fontsize=13.2)
        page.insert_text((60, 110), "Cloud & DevOps", fontsize=8.3)

    assert "skill_overflow_page_created" in _codes(draw, tmp_path)


def _attempt(name, pages, score=100):
    return LayoutVariantAttempt(
        name=name, pdf=Path(f"/tmp/{name}.pdf"),
        qa_report={"pages": pages, "human_taste": {"score": score}},
        status="passed", layout_options={},
    )


def test_selector_prefers_fewer_pages_at_equal_score():
    selection = select_best_layout_variant([_attempt("base", 12), _attempt("grouped", 10)])

    assert selection.selected.name == "grouped"


def test_selector_still_prefers_a_better_score_over_fewer_pages():
    selection = select_best_layout_variant([_attempt("base", 12, score=100), _attempt("grouped", 10, score=88)])

    assert selection.selected.name == "base"


def _passing_qa(*_args, **_kwargs):
    return {"pages": 2, "contact_hits": [], "has_logo": True, "has_watermark": True, "layout_issues": [],
            "human_taste": {"score": 100}}


def _render_recorder(tmp_path, seen):
    def render(_structured, _workdir, layout_options=None, output_name="output.pdf"):
        seen.append(dict(layout_options or {}))
        pdf = tmp_path / output_name
        pdf.write_bytes(b"%PDF")
        return pdf
    return render


def test_passing_forced_page_layout_also_tries_grouped_experiences(tmp_path):
    seen = []

    run_layout(structured={"name": "JEAN", "experiences": []}, workdir=tmp_path,
               render_pdf=_render_recorder(tmp_path, seen), run_qa=_passing_qa,
               base_options={"force_experiences_new_page": True, "force_page_break_before_experience_indexes": [2, 4]})

    assert len(seen) == 2
    assert seen[1]["force_experiences_new_page"] is False
    assert seen[1]["force_page_break_before_experience_indexes"] == []
    assert seen[1]["allow_grouping"] is True


def test_passing_grouped_layout_is_not_rendered_twice(tmp_path):
    seen = []

    run_layout(structured={"name": "JEAN", "experiences": []}, workdir=tmp_path,
               render_pdf=_render_recorder(tmp_path, seen), run_qa=_passing_qa,
               base_options={"force_experiences_new_page": False, "force_page_break_before_experience_indexes": [],
                             "allow_grouping": True})

    assert len(seen) == 1


def test_candidate_display_name_printed_by_the_renderer_is_not_a_foreign_fact():
    from src.qa import find_pdf_source_fidelity_issues

    # Yannick: the source PDF has no name as text; the renderer prints the
    # portal first name on each page header.
    issues = find_pdf_source_fidelity_issues(
        "YANNICK\nDéveloppeur Full Stack Senior\nStack principale\nStack Magique",
        source_text="Développeur Full Stack Senior .NET/Angular",
        structured_data={"name": "YANNICK", "experiences": [], "skills": []},
    )

    # "Stack principale" is a W hub taxonomy label the prompt imposes: allowed
    # too. A label outside the taxonomy is still reported.
    assert [issue["fact"] for issue in issues if issue["code"] == "pdf_fact_absent_from_source"] == ["Stack Magique"]


def _qa_report(*codes):
    return {"pages": 2, "contact_hits": [], "has_logo": True, "has_watermark": True,
            "layout_issues": [{"code": code, "page": 1} for code in codes], "content_integrity_issues": []}


def test_dense_but_acceptable_page_alone_stays_ready_and_visible():
    from src.qa import classify_qa_report

    status, warnings = classify_qa_report(_qa_report("page_dense_but_acceptable"))

    assert status == "passed"
    assert [w["code"] for w in warnings] == ["page_dense_but_acceptable"]


def test_dense_but_acceptable_with_another_layout_issue_is_still_draft():
    from src.qa import classify_qa_report

    status, warnings = classify_qa_report(_qa_report("page_dense_but_acceptable", "last_page_sparse"))

    assert status == "draft"
    assert {w["code"] for w in warnings} == {"page_dense_but_acceptable", "last_page_sparse"}


def test_run_qa_marks_advisory_only_report_as_passed(tmp_path, monkeypatch):
    from src import qa

    monkeypatch.setattr(qa, "find_layout_issues", lambda _doc: [{"code": "page_dense_but_acceptable", "page": 1}])
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((72, 120), "Développeur Java", fontsize=12)
    page.insert_image(fitz.Rect(400, 20, 500, 60), pixmap=fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 1051, 398), 0))
    page.insert_image(fitz.Rect(100, 300, 400, 600), pixmap=fitz.Pixmap(fitz.csRGB, fitz.IRect(0, 0, 1192, 1192), 0))
    path = tmp_path / "cv.pdf"
    doc.save(str(path))

    report = qa.run_qa(path)

    assert report["passed"] is True
    assert [i["code"] for i in report["layout_issues"]] == ["page_dense_but_acceptable"]


def test_advisory_layout_issue_with_content_issue_keeps_previous_draft_outcome():
    from src.qa import classify_qa_report

    report = _qa_report("page_dense_but_acceptable")
    report["content_integrity_issues"] = [{"code": "pdf_fact_absent_from_source"}]

    assert classify_qa_report(report)[0] == "draft"
