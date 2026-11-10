"""Lot 4 (2026-11) : réaction du worker aux défauts bloquants et demandes de
pagination des relecteurs (runners et rendus simulés, aucun appel LLM)."""
from pathlib import Path

import pytest

from src import main as worker_main
from src import storage
from src.layout import LayoutResult
from src.qa_defects import BLOCKING, WARNING
from src.revisions import classify_revision_intent, pagination_request
from src.structuring import build_whub_json

_SOURCE = "\n".join([
    "Zahia source",
    "Compétences: Python, Kubernetes, Terraform, conduite du changement, architecture cloud.",
    "Expériences: pilotage de projets data et industrialisation de plateformes internes.",
    "Réalisations: migration applicative, automatisation CI/CD, sécurisation des déploiements.",
    "Formation: école d'ingénieur, certifications cloud, ateliers agiles et mentorat technique.",
    "Langues: français, anglais professionnel, communication avec équipes produit et métier.",
])


# ------------------------------------------------------------ reviewer comments (corpus)

@pytest.mark.parametrize("body,goal,intent", [
    ("Fais tenir le CV sur moins de pages, sans retirer de contenu.", "fewer_pages", "layout_only"),
    ("Rééquilibre la mise en page entre les pages, sans retirer de contenu.", "rebalance", "layout_only"),
    ("Rééquilibre la mise en page entre les pages, sans retirer de contenu. éviter les répétitions dans la "
     "partie compétence notamment dans les titres", "rebalance", "content"),
    ("en terme de présentation, il faut remonter les expériences de la page 2 sur la page 1 dans la mesure du "
     "possible pour pas laisser un gros vide sur la page blanche. Mets en avant les 10 ans d'expérience en banque",
     "rebalance", "content"),
    ("verifie bien les saut de page et la qualité visuel globale", "rebalance", "layout_only"),
    ("Garde seulement les compétences les plus liées au poste visé.", None, "content"),
    ("Reprends exactement le texte du CV source pour ce passage, sans reformuler.", None, "unknown"),
])
def test_reviewer_comments_of_the_corpus_are_recognised(body, goal, intent):
    assert pagination_request([{"body": body, "comment_type": "revision"}]) == goal
    assert classify_revision_intent(body).kind == intent


def test_fewer_pages_wins_over_rebalance_and_history_comments_are_ignored():
    comments = [
        {"body": "Rééquilibre la mise en page", "comment_type": "revision"},
        {"body": "Fais tenir le CV sur moins de pages", "comment_type": "revision"},
        {"body": "moins de pages", "comment_type": "history"},
    ]
    assert pagination_request(comments) == "fewer_pages"
    assert pagination_request(comments[2:]) is None


# ------------------------------------------------------------ corrective prompt

def test_corrective_diagnostic_wraps_the_prompt_with_the_corrective_retry():
    prompts = []

    def runner(prompt, _timeout):
        prompts.append(prompt)
        return 0, '{"name": "ZAHIA", "title": "", "experiences": [], "formations": [], "skills": []}', ""

    for diagnostic in (None, "qa_blocking_content_defects: - truncated_text: « Apprendre à automatiser un »"):
        try:
            build_whub_json(_SOURCE, "", [], "Zahia", hermes_runner=runner, corrective_diagnostic=diagnostic)
        except Exception:  # noqa: BLE001 - fidelity gates on a minimal JSON; only the prompt matters
            pass
    assert "RETRY CORRECTIF" not in prompts[0]
    assert "RETRY CORRECTIF" in prompts[1] and "Apprendre à automatiser un" in prompts[1]


# ------------------------------------------------------------ process_job

class _Table:
    def __init__(self, log, name):
        self.log, self.name = log, name

    def select(self, *_a): return self
    def eq(self, *_a): return self
    def update(self, payload, *_a, **_k):
        self.log.append((self.name, payload))
        return self
    def execute(self): return type("Res", (), {"data": []})()


def _defect(code, severity=BLOCKING, origin="layout", loss=False, page=None):
    item = {"code": code, "severity": severity, "origin": origin, "content_loss": loss, "message": code}
    if page:
        item["page"] = page
    return item


def _qa(defects, **extra):
    report = {
        "passed": not any(d["severity"] == BLOCKING for d in defects), "pages": 2, "contact_hits": [],
        "bad_glyphs": False, "content_integrity_issues": [], "text_overflow_hits": [], "layout_issues": [],
        "has_logo": True, "has_watermark": True, "human_taste": {"score": 100},
        "pagination": {"page_fill": [0.9, 0.6], "warnings": []}, "defects": defects,
    }
    report.update(extra)
    return report


@pytest.fixture
def worker(monkeypatch, tmp_path):
    pdf = tmp_path / "output.pdf"
    pdf.write_bytes(b"%PDF")
    state = {"events": [], "saved": {}, "updates": [], "structure_calls": [], "layouts": [], "blocked": []}
    monkeypatch.setattr(worker_main.settings, "tmp_dir", str(tmp_path))
    monkeypatch.setattr(worker_main, "download_source", lambda job, workdir: pdf)
    monkeypatch.setattr(worker_main, "extract_pdf_text", lambda source: _SOURCE)
    monkeypatch.setattr(worker_main, "detect_page_furniture", lambda source: [])
    monkeypatch.setattr(worker_main, "_apply_source_wins_post_structuring", lambda structured, source: structured)

    def build(*args, **kwargs):
        state["structure_calls"].append(kwargs.get("corrective_diagnostic"))
        return {"name": "ZAHIA", "formations": [], "skills": [], "experiences": []}

    monkeypatch.setattr(worker_main, "build_whub_json", build)
    monkeypatch.setattr(worker_main, "emit_event", lambda rid, event, payload=None: state["events"].append((event, payload or {})))
    monkeypatch.setattr(worker_main, "save_version", lambda *a, **k: state["saved"].update({"args": a, "kwargs": k}) or {"id": "v1", "version_number": 1})
    monkeypatch.setattr(worker_main, "mark_request_blocked", lambda rid, reason: state["blocked"].append(reason))
    monkeypatch.setattr(worker_main.client, "table", lambda name: _Table(state["updates"], name))
    state["pdf"] = pdf
    return state


def _run_layout_sequence(state, reports, revision=None):
    def run_layout(**kwargs):
        state["layouts"].append(kwargs)
        report = reports[min(len(state["layouts"]) - 1, len(reports) - 1)]
        return LayoutResult(pdf=state["pdf"], qa_report=report, layout_options={}, attempts_count=1,
                            selected_variant="base", revision=revision)
    return run_layout


def test_content_defect_gets_one_corrective_structuring_when_a_model_is_configured(monkeypatch, worker):
    truncated = _defect("truncated_text", origin="content")
    truncated["items"] = [{"text": "Apprendre à automatiser un"}]
    monkeypatch.setattr(worker_main, "run_layout", _run_layout_sequence(worker, [_qa([truncated]), _qa([])]))
    monkeypatch.setattr(worker_main, "_llm_configured", lambda: True)

    worker_main.process_job({"id": "r1", "candidate_first_name": "ZAHIA", "instructions": ""})

    assert worker["structure_calls"][0] is None
    assert "Apprendre à automatiser un" in worker["structure_calls"][1]
    assert len(worker["structure_calls"]) == 2  # bounded: one corrective retry
    assert worker["saved"]["kwargs"]["request_status"] == "ready"
    saved_report = worker["saved"]["args"][3]
    assert saved_report["content_retry"] == {"codes": ["truncated_text"], "blocking_before": 1, "blocking_after": 0, "kept": True}


def test_content_defect_without_model_is_delivered_to_review_with_the_defect_first(monkeypatch, worker):
    truncated = _defect("truncated_text", origin="content")
    monkeypatch.setattr(worker_main, "run_layout", _run_layout_sequence(worker, [_qa([truncated, _defect("future_end_date", WARNING, "content")])]))
    monkeypatch.setattr(worker_main, "_llm_configured", lambda: False)

    worker_main.process_job({"id": "r1", "candidate_first_name": "ZAHIA", "instructions": ""})

    assert worker["structure_calls"] == [None]
    assert worker["saved"]["kwargs"]["request_status"] == "draft_ready"
    quality = worker["saved"]["args"][3]["quality_report"]
    assert [b["code"] for b in quality["hard_blockers"]] == ["truncated_text"]
    assert "future_end_date" in {w["code"] for w in quality["soft_warnings"]}
    assert "truncated_text" not in {w["code"] for w in quality["soft_warnings"]}
    assert not worker["blocked"]


def test_lost_content_blocks_the_request_but_keeps_the_version_visible(monkeypatch, worker):
    lost = _defect("content_missing_from_pdf", loss=True)
    monkeypatch.setattr(worker_main, "run_layout", _run_layout_sequence(worker, [_qa([lost])]))
    monkeypatch.setattr(worker_main, "_llm_configured", lambda: True)

    worker_main.process_job({"id": "r1", "candidate_first_name": "ZAHIA", "instructions": ""})

    assert worker["structure_calls"] == [None]  # layout defect: no model call
    assert worker["saved"]["kwargs"]["request_status"] == "draft_ready"
    assert worker["blocked"] and worker["blocked"][0].startswith("Contenu absent du PDF")
    event, payload = worker["events"][-1]
    assert event == "qa_failed"
    assert payload["blocking_defects"][0]["code"] == "content_missing_from_pdf"


def test_mark_request_blocked_sets_qa_failed_with_reason(monkeypatch):
    log = []
    monkeypatch.setattr(storage, "client", type("C", (), {"table": lambda self, name: _Table(log, name)})())
    storage.mark_request_blocked("r1", "Contenu absent du PDF : certifications 8/21")
    assert log[0][0] == "cv_requests"
    assert log[0][1]["status"] == "qa_failed"
    assert log[0][1]["last_error"].startswith("Contenu absent du PDF")


def test_pagination_request_reaches_run_layout_and_its_outcome_the_version(monkeypatch, worker):
    comments = [{"body": "Fais tenir le CV sur moins de pages, sans retirer de contenu.", "comment_type": "revision"}]

    class _Comments(_Table):
        def execute(self):
            return type("Res", (), {"data": comments if self.name == "cv_comments" else []})()

    monkeypatch.setattr(worker_main.client, "table", lambda name: _Comments(worker["updates"], name))
    outcome = {"goal": "fewer_pages", "improved": False, "previous_pages": 2, "new_pages": 2,
               "message": "Impossible de passer sous 2 pages sans retirer de contenu : …"}
    monkeypatch.setattr(worker_main, "run_layout", _run_layout_sequence(worker, [_qa([])], revision=outcome))

    worker_main.process_job({"id": "r1", "candidate_first_name": "ZAHIA", "instructions": ""})

    assert worker["layouts"][0]["pagination_goal"] == "fewer_pages"
    saved_report = worker["saved"]["args"][3]
    assert saved_report["revision_pagination"]["message"].startswith("Impossible de passer sous 2 pages")
    # Not applied: the reviewer must read why -> "à relire", never "ready" in silence.
    assert worker["saved"]["kwargs"]["request_status"] == "draft_ready"
    assert saved_report["draft_override_reason"] == "pagination_revision_not_possible"
    codes = {w["code"]: w for w in saved_report["quality_report"]["soft_warnings"]}
    assert codes["pagination_revision_not_possible"]["new_pages"] == 2
    assert ("pagination_revision_detected", {"goal": "fewer_pages"}) in worker["events"]
