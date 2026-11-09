"""Pagination by measured height (lot 1 of the PDF quality work, 2026-11).

Page breaks follow the room really left on the page: no density budget, no
forced break, a heading kept with its first lines, long experiences split
between lines, short tails rebalanced. The QA measures the same things on the
rendered PDF (report["pagination"], warnings only for now).
"""
import importlib.util
import io
import json
import subprocess
import sys
import tempfile
from pathlib import Path

import fitz
import pytest

from src.qa import collect_pagination_metrics, run_qa, QAError

RENDERER = Path(__file__).resolve().parents[1] / "renderer" / "whub_cv_renderer.py"


@pytest.fixture(scope="module")
def renderer_module():
    spec = importlib.util.spec_from_file_location("whub_cv_renderer_pagination", RENDERER)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    module.prep_assets()
    module.register_fonts(module.ensure_poppins())
    return module


def _render(data, tmp_path: Path) -> Path:
    input_path = tmp_path / "input.json"
    output_path = tmp_path / "output.pdf"
    input_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    result = subprocess.run([sys.executable, str(RENDERER), str(input_path), str(output_path)],
                            text=True, capture_output=True, timeout=180)
    assert result.returncode == 0, result.stderr or result.stdout
    return output_path


def _cv(experiences, skills=None):
    return {
        "name": "LINO",
        "title": "Chef de projet",
        "formations": [{"date": "2010", "degree": "Master", "school": "Université"}],
        "skills": skills or [{"category": "Gestion", "items": ["Agile", "Scrum"]}],
        "experiences": experiences,
    }


def _exp(index, bullets, text="de cadrage, pilotage et recette des évolutions applicatives"):
    return {
        "date": f"20{10 + index} - 20{11 + index}",
        "role": f"Chef de projet chez Client {index}",
        "company_highlight": f"Client {index}",
        "sections": [{"heading": "Missions clés", "content": [f"Mission {index}-{j} {text}" for j in range(bullets)]}],
    }


def _codes(pagination):
    return [w["code"] for w in pagination["warnings"]]


def _normalized_text(pdf_path: Path) -> str:
    doc = fitz.open(str(pdf_path))
    return " ".join(" ".join(doc[i].get_text().split()) for i in range(doc.page_count))


# ------------------------------------------------------------ plan_section_break

def test_plan_takes_whole_section_when_it_fits(renderer_module):
    plan = renderer_module.plan_section_break([1, 2, 1], 10.0, 0.0, 45.0)
    assert plan == (3, 0, 4)


def test_plan_splits_a_bullet_with_two_lines_each_side(renderer_module):
    # 3 one-line bullets fit, the 5-line one is cut 2 / 3.
    plan = renderer_module.plan_section_break([1, 1, 1, 5], 10.0, 0.0, 55.0)
    assert plan == (3, 2, 5)


def test_plan_never_leaves_a_single_line_of_a_bullet_on_either_page(renderer_module):
    # Room for 1 line of the 4-line bullet: it moves whole, 3 lines continue.
    assert renderer_module.plan_section_break([2, 4], 10.0, 0.0, 30.0) == (1, 0, 2)
    # A 3-line bullet cannot be cut (2 + 1 would strand a line).
    assert renderer_module.plan_section_break([3, 3, 3], 10.0, 0.0, 85.0) == (2, 0, 6)


def test_plan_keeps_three_lines_for_a_continuation(renderer_module):
    # Everything but the last one-line bullet fits: a one-line "(suite)" is
    # refused, the section breaks earlier so three lines continue.
    plan = renderer_module.plan_section_break([1, 1, 1, 1, 1, 1], 10.0, 0.0, 55.0)
    assert plan == (3, 0, 3)


# ------------------------------------------------------------ rendering

def test_second_experience_stays_on_page_one_when_it_fits(tmp_path):
    # The former renderer always sent experience #2 to page 2 (idx == 1 rule).
    pdf = _render(_cv([_exp(0, 3), _exp(1, 3)]), tmp_path)
    doc = fitz.open(str(pdf))

    assert doc.page_count == 1
    assert "Client 1" in doc[0].get_text()


def test_long_experience_is_split_between_lines_not_pushed_whole(tmp_path):
    data = _cv([_exp(0, 4), _exp(1, 60)])
    pdf = _render(data, tmp_path)
    doc = fitz.open(str(pdf))
    pagination = collect_pagination_metrics(doc)

    # The long experience starts on page 1 under the first one.
    assert "Chef de projet chez Client 1" in " ".join(doc[0].get_text().split())
    assert pagination["first_page_has_experience"]
    assert pagination["page_fill"][0] > 0.85
    assert not {"heading_orphaned_at_page_bottom", "short_continuation", "page_underfilled"} & set(_codes(pagination))
    text = _normalized_text(pdf)
    for exp in data["experiences"]:
        for item in exp["sections"][0]["content"]:
            assert item in text


def test_split_bullet_keeps_all_its_words(tmp_path):
    # ReportLab split pieces return '' from getPlainText: the end of a bullet
    # cut across pages used to vanish.
    long_tail = ("Prise en charge progressive du périmètre, transfert, autonomie complète, "
                 "formalisation des procédures et des modes opératoires de recette ") * 4
    bullets = [f"Mission courte numéro {j} de cadrage et de recette" for j in range(48)]
    bullets.insert(40, "Description longue : " + long_tail + "FIN-DU-PARAGRAPHE")
    data = _cv([{"date": "2020 - 2024", "role": "Testeur chez Client", "company_highlight": "Client",
                 "sections": [{"heading": "Missions clés", "content": bullets}]}])
    pdf = _render(data, tmp_path)

    text = _normalized_text(pdf)
    assert "FIN-DU-PARAGRAPHE" in text
    for item in bullets:
        assert " ".join(item.split()) in text


def test_section_heading_is_not_left_alone_at_page_bottom(tmp_path):
    experiences = [_exp(i, 5) for i in range(3)]
    experiences[2]["sections"].append({"heading": "Environnement", "content": [f"Outil {k}" for k in range(8)]})
    for filler in range(3, 12):
        experiences.append(_exp(filler, 4 + filler % 3))
    pdf = _render(_cv(experiences), tmp_path)
    pagination = collect_pagination_metrics(fitz.open(str(pdf)))

    assert "heading_orphaned_at_page_bottom" not in _codes(pagination)
    assert "short_continuation" not in _codes(pagination)


def test_short_last_page_is_rebalanced_without_adding_a_page(renderer_module, tmp_path):
    data = _cv([_exp(i, 6) for i in range(12)])
    plain = renderer_module.Renderer(io.BytesIO())
    plain.render(data)
    assert plain.page == 3 and plain._page_fill(3) < 0.35  # the case under test

    pdf = _render(data, tmp_path)
    doc = fitz.open(str(pdf))
    pagination = collect_pagination_metrics(doc)

    assert doc.page_count == 3
    assert pagination["page_fill"][-1] >= 0.35
    assert pagination["page_fill"][-2] >= 0.60
    assert not set(_codes(pagination)) & {"last_page_nearly_empty", "page_underfilled"}


def test_explicit_forced_break_is_still_honoured(tmp_path):
    data = _cv([_exp(0, 12), _exp(1, 12), _exp(2, 3)])
    data["_layout"] = {"force_page_break_before_experience_indexes": [2]}
    pdf = _render(data, tmp_path)
    doc = fitz.open(str(pdf))

    assert "Client 2" not in doc[0].get_text()


# ------------------------------------------------------------ QA measures

def _page(doc):
    return doc.new_page(width=595, height=842)


def test_qa_pagination_flags_underfilled_page_last_page_and_missing_first_experience():
    doc = fitz.open()
    p1 = _page(doc)
    p1.insert_text((60, 300), "C O M P É T E N C E S", fontname="helv", fontsize=12)
    p2 = _page(doc)
    for i in range(10):
        p2.insert_text((60, 90 + i * 12), f"• Ligne {i}", fontsize=8)
    p3 = _page(doc)
    p3.insert_text((60, 90), "• Dernière ligne", fontsize=8)

    pagination = collect_pagination_metrics(doc)
    codes = _codes(pagination)

    assert "page_underfilled" in codes  # page 1 (included) and page 2
    assert {w["page"] for w in pagination["warnings"] if w["code"] == "page_underfilled"} == {1, 2}
    assert "last_page_nearly_empty" in codes
    assert "first_page_without_experience" in codes
    assert not pagination["first_page_has_experience"]


def test_qa_pagination_flags_heading_left_at_page_bottom():
    doc = fitz.open()
    p1 = _page(doc)
    for i in range(55):
        p1.insert_text((60, 90 + i * 12), f"• Ligne {i}", fontsize=8)
    p1.insert_text((60, 790), "Missions clés", fontname="hebo", fontsize=8.45)
    p2 = _page(doc)
    p2.insert_text((60, 90), "Missions clés (suite)", fontname="hebo", fontsize=8.45)
    for i in range(5):
        p2.insert_text((60, 102 + i * 12), f"• Suite {i}", fontsize=8)

    codes = _codes(collect_pagination_metrics(doc))

    assert "heading_orphaned_at_page_bottom" in codes


def test_qa_pagination_flags_two_line_continuation():
    doc = fitz.open()
    p1 = _page(doc)
    for i in range(60):
        p1.insert_text((60, 90 + i * 12), f"• Ligne {i}", fontsize=8)
    p2 = _page(doc)
    p2.insert_text((60, 90), "Missions clés (suite)", fontname="hebo", fontsize=8.45)
    p2.insert_text((60, 102), "• Reste 1", fontsize=8)
    p2.insert_text((60, 114), "• Reste 2", fontsize=8)
    p2.insert_text((60, 130), "Environnement", fontname="hebo", fontsize=8.45)
    p2.insert_text((60, 142), "• Outil", fontsize=8)

    codes = _codes(collect_pagination_metrics(doc))

    assert "short_continuation" in codes


def test_run_qa_reports_pagination_as_warnings_only(tmp_path):
    data = _cv([_exp(0, 3)])
    pdf = _render(data, tmp_path)
    doc = fitz.open()
    doc.insert_pdf(fitz.open(str(pdf)))
    _page(doc).insert_text((60, 90), "• Une ligne seule", fontsize=8)  # nearly empty last page
    path = tmp_path / "with_tail.pdf"
    doc.save(str(path))

    try:
        report = run_qa(path, structured_data=None)
    except QAError as error:
        report = error.report

    assert "last_page_nearly_empty" in _codes(report["pagination"])
    layout_codes = {issue["code"] for issue in report["layout_issues"]}
    assert not layout_codes & {"last_page_nearly_empty", "page_underfilled", "heading_orphaned_at_page_bottom",
                               "short_continuation", "first_page_without_experience"}
