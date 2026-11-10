"""Lot 4 (2026-11) : hiérarchie des défauts du PDF rendu et réaction.

Bloquant -> réessai ciblé (variantes de mise en page, puis restructuration
corrective si un modèle est configuré) -> « à relire » ou « bloqué ».
Avertissement -> point à vérifier. Journal -> corrections tracées, sans bruit.
"""
import json
import subprocess
import sys
from pathlib import Path

import fitz
import pytest

from src.layout import run_layout
from src.layout.pagination import (
    blank_amount,
    describe_revision_outcome,
    pagination_cost,
    repair_variant_options,
)
from src.qa import QAError, classify_qa_report, collect_json_pdf_coverage, printed_content_warnings, run_qa
from src.qa_defects import (
    BLOCKING,
    INFO,
    WARNING,
    blocking_defects,
    collect_defects,
    corrective_diagnostic,
    has_content_loss,
    rule_for,
    truncation_reproduces_source,
)

RENDERER = Path(__file__).resolve().parents[1] / "renderer" / "whub_cv_renderer.py"


def _base_report(**overrides):
    report = {
        "passed": True,
        "pages": 2,
        "contact_hits": [],
        "bad_glyphs": False,
        "content_integrity_issues": [],
        "text_overflow_hits": [],
        "layout_issues": [],
        "has_logo": True,
        "has_watermark": True,
        "pagination": {"page_fill": [0.95, 0.5], "warnings": []},
        "content_warnings": [],
        "skills_cleanup": None,
    }
    report.update(overrides)
    return report


def _codes(defects, severity=None):
    return sorted(d["code"] for d in defects if severity is None or d["severity"] == severity)


# ------------------------------------------------------------ classification

def test_intermediate_page_under_40_percent_is_blocking_between_40_and_60_a_warning():
    report = _base_report(pagination={"page_fill": [0.35, 0.55, 0.9], "warnings": [
        {"code": "page_underfilled", "page": 1, "fill": 0.35, "message": "Page 1 remplie à 35%"},
        {"code": "page_underfilled", "page": 2, "fill": 0.55, "message": "Page 2 remplie à 55%"},
    ]})
    defects = collect_defects(report)
    assert _codes(defects, BLOCKING) == ["page_nearly_empty"]
    assert _codes(defects, WARNING) == ["page_underfilled"]
    assert next(d for d in defects if d["code"] == "page_nearly_empty")["page"] == 1


def test_orphan_heading_is_blocking_last_page_and_short_suite_are_warnings():
    report = _base_report(pagination={"page_fill": [0.95, 0.2], "warnings": [
        {"code": "heading_orphaned_at_page_bottom", "page": 1, "message": "Titre isolé", "lines_under": 0},
        {"code": "last_page_nearly_empty", "page": 2, "fill": 0.2, "message": "Dernière page remplie à 20%"},
        {"code": "short_continuation", "page": 2, "message": "Suite de 1 ligne"},
        {"code": "first_page_without_experience", "page": 1, "message": "Pas d'expérience"},
    ]})
    defects = collect_defects(report)
    assert _codes(defects, BLOCKING) == ["heading_orphaned_at_page_bottom"]
    assert _codes(defects, WARNING) == ["first_page_without_experience", "last_page_nearly_empty", "short_continuation"]


def test_text_overflow_and_missing_content_are_blocking_and_missing_content_is_a_loss():
    report = _base_report(
        text_overflow_hits=[{"page": 1, "side": "bottom", "text": "Microsoft .NET"}],
        content_warnings=[{"code": "content_missing_from_pdf", "message": "certifications 8/21",
                           "items": [{"section": "certifications", "text": "AZ-104"}]}],
    )
    defects = collect_defects(report)
    assert _codes(defects, BLOCKING) == ["content_missing_from_pdf", "text_overflow"]
    assert has_content_loss(defects)
    assert not has_content_loss([d for d in defects if d["code"] == "text_overflow"])


def test_log_codes_are_info_and_reviewer_checks_are_warnings():
    report = _base_report(content_warnings=[
        {"code": "date_normalized", "message": "Date mise au format"},
        {"code": "bullet_rejoined", "message": "Puce recollée"},
        {"code": "future_end_date", "message": "Date future"},
        {"code": "content_language_not_french", "message": "Anglais"},
        {"code": "description_too_short", "message": "Courte"},
        {"code": "code_inconnu_du_lot_9", "message": "?"},
    ], skills_cleanup={"code": "skills_cleanup"})
    defects = collect_defects(report)
    assert not blocking_defects(defects)
    assert _codes(defects, INFO) == ["bullet_rejoined", "date_normalized"]
    # An unknown code is never ignored: warning.
    assert _codes(defects, WARNING) == [
        "code_inconnu_du_lot_9", "content_language_not_french", "description_too_short", "future_end_date", "skills_cleaned",
    ]
    assert rule_for("code_inconnu_du_lot_9").severity == WARNING


def test_truncated_bullet_is_blocking_unless_the_source_is_cut_the_same_way():
    source = (
        "Création de nouvelles feature avec tout le scope UX (Recherche quantitative, itw,\n"
        "Design system, ateliers\n"
        "Apprendre à automatiser un pipeline de tests de bout en bout\n"
    )
    faithful = {"path": "x", "reason": "parenthese_ouverte",
                "text": "Création de nouvelles feature avec tout le scope UX (Recherche quantitative, itw Design system, ateliers"}
    cut = {"path": "y", "reason": "fin_sur_mot_outil", "text": "Apprendre à automatiser un"}
    assert truncation_reproduces_source(faithful, source)
    assert not truncation_reproduces_source(cut, source)
    report = _base_report(content_warnings=[{"code": "truncated_text", "message": "2", "items": [faithful, cut]}])
    defects = collect_defects(report, source)
    assert _codes(defects, BLOCKING) == ["truncated_text"]
    assert _codes(defects, WARNING) == ["truncated_in_source"]
    blocking = blocking_defects(defects)[0]
    assert blocking["origin"] == "content" and blocking["items"][0]["text"] == "Apprendre à automatiser un"


def test_truncation_check_reads_the_whole_json_text_not_the_200_first_characters():
    long_text = "Mise en place " + "du suivi des incidents et des demandes " * 6 + "(outil interne, revue hebdomadaire"
    source = long_text + "\n2019-2021\n"
    data = {"experiences": [{"sections": [{"content": [long_text]}]}]}
    item = {"path": "experiences[0].sections[0].content[0]", "reason": "parenthese_ouverte", "text": long_text[:200]}
    report = _base_report(content_warnings=[{"code": "truncated_text", "message": "1", "items": [item]}])
    defects = collect_defects(report, source, data)
    assert _codes(defects) == ["truncated_in_source"]


def test_printed_placeholders_and_source_header_are_blocking():
    warnings = printed_content_warnings(
        "2001 Commercial — Non spécifié\nFormation ()\n",
        {"experiences": [{"role": "Consultant", "sections": [{"content": ["CV - Page 2 / 4"]}]}]},
    )
    codes = {w["code"] for w in warnings}
    assert "placeholder_printed" in codes
    defects = collect_defects(_base_report(content_warnings=warnings))
    assert "placeholder_printed" in _codes(defects, BLOCKING)
    assert not printed_content_warnings("Développement d'API (REST) et N° de lot\n", {"experiences": []})


def test_corrective_diagnostic_lists_content_defects_only():
    defects = collect_defects(_base_report(
        pagination={"page_fill": [0.3, 0.9], "warnings": [{"code": "page_underfilled", "page": 1, "fill": 0.3, "message": "p1"}]},
        content_warnings=[{"code": "truncated_text", "message": "1", "items": [
            {"path": "p", "reason": "fin_sur_mot_outil", "text": "Superviser les APIs : temps de réponse, erreurs et"}]}],
    ))
    text = corrective_diagnostic(defects)
    assert "truncated_text" in text and "Superviser les APIs" in text
    assert "page_nearly_empty" not in text
    assert corrective_diagnostic([]) == ""


def test_blocking_defect_never_passes_classification():
    report = _base_report(defects=[{"code": "heading_orphaned_at_page_bottom", "severity": BLOCKING, "origin": "layout"}])
    status, warnings = classify_qa_report(report)
    assert status == "draft"
    assert warnings[0]["code"] == "heading_orphaned_at_page_bottom"
    assert classify_qa_report(_base_report(defects=[{"code": "future_end_date", "severity": WARNING}]))[0] == "passed"


def test_coverage_counts_a_long_item_drawn_in_pieces_as_present(tmp_path):
    doc = fitz.open()
    page = doc.new_page(width=595, height=842)
    page.insert_text((60, 100), "Backend Python Flask · APIs REST", fontsize=8)
    page.insert_text((60, 112), "et MongoDB · Déploiement Azure Cloud", fontsize=8)
    path = tmp_path / "c.pdf"
    doc.save(str(path))
    data = {"skills": [{"category": "", "items": ["Backend Python/Flask, APIs REST et MongoDB. Déploiement Azure Cloud"]}]}
    coverage = collect_json_pdf_coverage(fitz.open(str(path)), data)
    assert coverage["missing_count"] == 0
    data["skills"][0]["items"].append("Kubernetes Helm Terraform Ansible")
    assert collect_json_pdf_coverage(fitz.open(str(path)), data)["missing_count"] == 1


# ------------------------------------------------------------ deterministic retry

def _fake_layout(reports_by_variant):
    """render_pdf / run_qa doubles: the QA report depends on the options."""

    def render_pdf(structured, workdir, layout_options=None, output_name="output.pdf"):
        path = Path(workdir) / output_name
        path.write_text(json.dumps(layout_options or {}, sort_keys=True))
        return path

    def run_qa(pdf, **_kwargs):
        options = json.loads(Path(pdf).read_text())
        for predicate, report in reports_by_variant:
            if predicate(options):
                return report
        raise AssertionError(options)

    return render_pdf, run_qa


def _report(pages, fills, *, blocking=(), warnings=()):
    defects = [{"code": c, "severity": BLOCKING, "origin": "layout", "page": 1, "message": c} for c in blocking]
    defects += [{"code": c, "severity": WARNING, "origin": "layout", "message": c} for c in warnings]
    return _base_report(pages=pages, pagination={"page_fill": fills, "warnings": []}, defects=defects,
                        human_taste={"score": 100}, passed=not blocking)


def test_blocking_layout_defect_is_repaired_by_a_renderer_variant(tmp_path):
    render_pdf, run_qa = _fake_layout([
        (lambda o: o.get("min_lines_under_heading") == 3, _report(3, [0.9, 0.9, 0.5])),
        (lambda o: True, _report(3, [0.9, 0.9, 0.5], blocking=["heading_orphaned_at_page_bottom"])),
    ])
    result = run_layout(structured={"name": "LINO", "experiences": []}, workdir=tmp_path,
                        render_pdf=render_pdf, run_qa=run_qa, base_options={"allow_grouping": True})
    assert result.selected_variant == "repair_keep_with_next"
    assert result.repair == {"initial_blocking": ["heading_orphaned_at_page_bottom"],
                             "tried": ["repair_keep_with_next"], "repaired": True}
    assert not blocking_defects(result.qa_report["defects"])


def test_blocking_layout_defect_that_persists_is_kept_and_reported(tmp_path):
    render_pdf, run_qa = _fake_layout([
        (lambda o: True, _report(2, [0.3, 0.9], blocking=["page_nearly_empty"])),
    ])
    result = run_layout(structured={"name": "LINO", "experiences": []}, workdir=tmp_path,
                        render_pdf=render_pdf, run_qa=run_qa, base_options={"allow_grouping": True})
    assert result.repair["repaired"] is False
    assert len(result.repair["tried"]) == 3  # bounded
    assert classify_qa_report(result.qa_report)[0] == "draft"


def test_repair_variants_only_for_layout_blocking_defects():
    content_only = {"defects": [{"code": "truncated_text", "severity": BLOCKING, "origin": "content"}]}
    assert repair_variant_options({}, content_only) == []
    names = [n for n, _ in repair_variant_options({}, {"defects": [
        {"code": "text_overflow", "severity": BLOCKING, "origin": "layout"}]})]
    assert names == ["repair_compact", "repair_grouped"]


def test_compact_spacing_kept_only_when_it_saves_a_page(tmp_path):
    render_pdf, run_qa = _fake_layout([
        (lambda o: o.get("spacing") == "compact", _report(1, [0.98])),
        (lambda o: True, _report(2, [0.96, 0.18], warnings=["last_page_nearly_empty"])),
    ])
    result = run_layout(structured={"name": "LINO", "experiences": []}, workdir=tmp_path,
                        render_pdf=render_pdf, run_qa=run_qa, base_options={"allow_grouping": True})
    assert result.selected_variant == "page_saving_compact"
    assert result.repair.get("page_saved") is True

    render_pdf, run_qa = _fake_layout([
        (lambda o: o.get("spacing") == "compact", _report(2, [0.99, 0.10])),
        (lambda o: True, _report(2, [0.96, 0.18])),
    ])
    (tmp_path / "b").mkdir()
    result = run_layout(structured={"name": "LINO", "experiences": []}, workdir=tmp_path / "b",
                        render_pdf=render_pdf, run_qa=run_qa, base_options={"allow_grouping": True})
    assert result.selected_variant == "base"


def test_pagination_cost_orders_blocking_then_pages_then_blank():
    clean_long = _report(3, [0.95, 0.95, 0.5])
    clean_short = _report(2, [0.95, 0.9])
    broken_short = _report(2, [0.95, 0.9], blocking=["text_overflow"])
    assert sorted([broken_short, clean_long, clean_short], key=pagination_cost) == [clean_short, clean_long, broken_short]
    assert blank_amount([0.5, 0.5, 0.2]) == pytest.approx(1.15)


# ------------------------------------------------------------ compact renderer (real rendering)

def _render(data, path: Path) -> Path:
    input_path = path.with_suffix(".json")
    input_path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")
    result = subprocess.run([sys.executable, str(RENDERER), str(input_path), str(path)],
                            text=True, capture_output=True, timeout=180)
    assert result.returncode == 0, result.stderr or result.stdout
    return path


def _cv(bullets):
    return {
        "name": "LINO",
        "title": "Chef de projet",
        "formations": [{"date": "2010", "degree": "Master", "school": "Université"}],
        "skills": [{"category": "Gestion", "items": ["Agile", "Scrum"]}],
        "experiences": [{
            "date": f"20{10 + i} - 20{11 + i}", "role": f"Chef de projet chez Client {i}", "company_highlight": f"Client {i}",
            "sections": [{"heading": "Missions clés", "content": [
                f"Mission {i}-{j} de cadrage, pilotage et recette des évolutions applicatives" for j in range(bullets)]}],
        } for i in range(6)],
    }


def test_compact_spacing_keeps_every_word_and_takes_less_height(tmp_path):
    data = _cv(7)
    normal = _render(data, tmp_path / "normal.pdf")
    compact = _render({**data, "_layout": {"spacing": "compact"}}, tmp_path / "compact.pdf")

    def text(pdf):
        doc = fitz.open(str(pdf))
        return " ".join(" ".join(doc[i].get_text().split()) for i in range(doc.page_count))

    def sizes(pdf):
        doc = fitz.open(str(pdf))
        return sorted({round(span["size"], 2) for page in doc for block in page.get_text("dict")["blocks"]
                       for line in block.get("lines", []) for span in line["spans"]})

    assert text(normal).split().count("Mission") == text(compact).split().count("Mission") == 42
    assert sizes(normal) == sizes(compact)  # same font sizes, tighter spacing only
    normal_report = _qa(normal, data)
    compact_report = _qa(compact, data)
    assert compact_report["content_coverage"]["missing_count"] == 0
    assert (compact_report["pages"], -sum(compact_report["pagination"]["page_fill"])) <= (normal_report["pages"], 0)
    assert sum(compact_report["pagination"]["page_fill"]) < sum(normal_report["pagination"]["page_fill"])


def _qa(pdf, data):
    try:
        return run_qa(pdf, structured_data=data)
    except QAError as error:
        return error.report


# ------------------------------------------------------------ revision outcome

def test_revision_outcome_says_when_fewer_pages_is_impossible():
    previous = _report(2, [0.99, 0.79])
    outcome = describe_revision_outcome(goal="fewer_pages", previous_report=previous, chosen_report=_report(2, [0.99, 0.79]))
    assert outcome["improved"] is False
    assert outcome["message"].startswith("Impossible de passer sous 2 pages sans retirer de contenu")

    outcome = describe_revision_outcome(goal="rebalance", previous_report=previous, chosen_report=_report(2, [0.99, 0.79]))
    assert outcome["improved"] is False and "déjà équilibrée" in outcome["message"]


def test_revision_outcome_reports_pages_saved_or_blank_removed():
    old = {"pages": 6, "layout_metrics": [{"used_ratio": r} for r in (0.5, 0.57, 0.53, 0.56, 0.53, 0.23)]}
    outcome = describe_revision_outcome(goal="fewer_pages", previous_report=old, chosen_report=_report(3, [0.98, 0.95, 0.96]))
    assert outcome["improved"] is True
    assert outcome["message"].startswith("Mise en page resserrée : 6 pages -> 3")
    outcome = describe_revision_outcome(goal="rebalance", previous_report=_report(3, [0.95, 0.45, 0.8]),
                                        chosen_report=_report(3, [0.95, 0.9, 0.35]))
    assert outcome["improved"] is True and outcome["message"].startswith("Pages rééquilibrées")


def test_pagination_goal_picks_the_variant_with_fewer_pages(tmp_path):
    render_pdf, run_qa = _fake_layout([
        (lambda o: o.get("spacing") == "compact", _report(2, [0.97, 0.9])),
        (lambda o: True, _report(3, [0.97, 0.95, 0.3])),
    ])
    previous = _report(3, [0.97, 0.95, 0.3])
    result = run_layout(structured={"name": "LINO", "experiences": []}, workdir=tmp_path,
                        render_pdf=render_pdf, run_qa=run_qa, base_options={"allow_grouping": True},
                        pagination_goal="fewer_pages", previous_report=previous)
    assert result.selected_variant == "revision_compact"
    assert result.revision["improved"] is True and result.revision["new_pages"] == 2
