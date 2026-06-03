import logging
import time
from time import perf_counter
from pathlib import Path
from datetime import datetime, timezone
import shutil
from typing import cast
from .config import settings
from .supabase_client import client
from .events import emit_event
from .extraction import download_source, extract_pdf_text
from .structuring import (
    build_whub_json,
    assert_no_contact_in_json,
    enforce_client_first_name,
    normalize_candidate_first_name,
    infer_forbidden_candidate_identity_terms,
    classify_structuring_error,
)
from .rendering import render_pdf
from .qa import run_qa, classify_qa_report
from .storage import next_version_number, save_version
from .layout_packing import build_layout_packing_options
from .layout_variants import run_bounded_layout_variant_loop
from .preflight import run_startup_preflight

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO), format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("whub-cv-worker")

def claim_next_job() -> dict | None:
    res = client.rpc("claim_next_cv_request", {"worker_name": settings.worker_name}).execute()
    return res.data[0] if res.data else None

def fail_job(job: dict, error: str | Exception, status: str = "failed") -> None:
    classified = classify_structuring_error(error)
    safe_error = classified["message"][:500]
    client.table("cv_requests").update({
        "status": status,
        "last_error": safe_error,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", job["id"]).execute()
    emit_event(job["id"], status, {"error": safe_error, "error_category": classified["category"]})


def forbidden_candidate_name_parts(candidate_first_name: str | None, source_text: str | None = None) -> list[str]:
    cleaned = " ".join(str(candidate_first_name or "").split())
    normalized_first = normalize_candidate_first_name(cleaned)
    forbidden: list[str] = []
    if cleaned and normalized_first:
        tokens = cleaned.split(" ")
        for token in tokens[1:]:
            candidate = token.strip(" ,;:/\\")
            if len(candidate) >= 3 and candidate.upper() != normalized_first and candidate not in forbidden:
                forbidden.append(candidate)
    for candidate in infer_forbidden_candidate_identity_terms(source_text or "", candidate_first_name):
        if candidate not in forbidden:
            forbidden.append(candidate)
    return forbidden


def _build_revision_history_comment(version: dict) -> dict:
    version_number = version.get("version_number")
    qa_status = version.get("qa_status") or "unknown"
    qa_report = version.get("qa_report") if isinstance(version, dict) else None
    layout_issues = qa_report.get("layout_issues") if isinstance(qa_report, dict) else []
    issue_summaries: list[str] = []
    if isinstance(layout_issues, list):
        for issue in layout_issues:
            if not isinstance(issue, dict):
                continue
            code = str(issue.get("code") or "").strip()
            message = str(issue.get("message") or issue.get("snippet") or "").strip()
            summary = code or "point_qualite"
            if message:
                summary = f"{summary}: {message}"
            issue_summaries.append(summary)
            if len(issue_summaries) >= 3:
                break
    body = f"Historique utile: version V{version_number} (qa={qa_status})."
    if issue_summaries:
        body += " Points qualité précédents: " + "; ".join(issue_summaries) + "."
    return {"body": body, "comment_type": "history"}


def process_job(job: dict) -> None:
    total_start = perf_counter()
    timings: dict[str, float] = {}
    request_id = job["id"]
    workdir = Path(settings.tmp_dir) / request_id
    if workdir.exists():
        shutil.rmtree(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    emit_event(request_id, "worker_claimed")

    stage_start = perf_counter()
    source = download_source(job, workdir)
    timings["download_source"] = perf_counter() - stage_start

    stage_start = perf_counter()
    text = extract_pdf_text(source)
    timings["extract_text"] = perf_counter() - stage_start
    emit_event(request_id, "extraction_done", {"chars": len(text)})

    stage_start = perf_counter()
    comments_res = client.table("cv_comments").select("body,comment_type").eq("request_id", request_id).eq("resolved", False).execute()
    timings["load_comments"] = perf_counter() - stage_start

    history_comments: list[dict] = []
    current_version_id = job.get("current_version_id")
    if current_version_id:
        version_res = client.table("cv_versions").select("version_number,qa_status,qa_report").eq("id", current_version_id).execute()
        if version_res.data:
            history_comments.append(_build_revision_history_comment(cast(dict, version_res.data[0])))

    stage_start = perf_counter()
    comments_for_prompt = history_comments + [cast(dict, comment) for comment in (comments_res.data or [])]
    structured = build_whub_json(text, job.get("instructions") or "", comments_for_prompt, job.get("candidate_first_name"))
    enforce_client_first_name(structured, job.get("candidate_first_name"))
    timings["hermes_structuring"] = perf_counter() - stage_start

    stage_start = perf_counter()
    assert_no_contact_in_json(structured)
    version_number = next_version_number(request_id)
    layout_options = build_layout_packing_options(structured)
    forbidden_names = forbidden_candidate_name_parts(job.get("candidate_first_name"), text)
    variant_selection = run_bounded_layout_variant_loop(
        structured=structured,
        workdir=workdir,
        base_options=layout_options,
        render_pdf=render_pdf,
        run_qa=run_qa,
        forbidden_names=forbidden_names,
        source_text=text,
    )
    timings["render_pdf_qa_layout_variants"] = perf_counter() - stage_start
    if variant_selection.hard_failure is not None:
        fail_job(job, str(variant_selection.hard_failure.qa_report), "qa_failed")
        return
    if variant_selection.selected is None or variant_selection.selected_pdf is None or variant_selection.selected_report is None:
        fail_job(job, "No layout variant produced a QA report", "failed")
        return
    pdf = variant_selection.selected_pdf
    qa_report = variant_selection.selected_report
    if len(variant_selection.attempts) > 1:
        emit_event(
            request_id,
            "layout_variant_selected",
            {
                "selected": variant_selection.selected.name,
                "attempts": [
                    {
                        "name": attempt.name,
                        "status": attempt.status,
                        "score": attempt.score,
                    }
                    for attempt in variant_selection.attempts
                ],
            },
        )

    final_qa_status, layout_warnings = classify_qa_report(qa_report)
    if final_qa_status == "failed":
        fail_job(job, str(qa_report), "qa_failed")
        return
    request_status = "draft_ready" if final_qa_status == "draft" else "ready"
    version_qa_status = "draft" if final_qa_status == "draft" else "passed"

    stage_start = perf_counter()
    version_id = save_version(
        request_id,
        version_number,
        structured,
        pdf,
        qa_report,
        request_status=request_status,
        qa_status=version_qa_status,
    )
    client.table("cv_comments").update({"resolved": True}).eq("request_id", request_id).eq("comment_type", "revision").execute()
    event_payload = {"version_id": version_id, "version_number": version_number}
    if request_status == "draft_ready":
        event_payload["layout_warnings"] = layout_warnings
    emit_event(request_id, request_status, event_payload)
    timings["upload_and_finalize"] = perf_counter() - stage_start
    timings["total"] = perf_counter() - total_start
    log.info("job timings request_id=%s %s", request_id, " ".join(f"{key}={value:.2f}s" for key, value in timings.items()))

def main() -> None:
    log.info("starting worker %s", settings.worker_name)
    preflight_report = run_startup_preflight()
    log.info(
        "startup preflight ok renderer=%s assets_dir=%s fonts_dir=%s fonts_source=%s supabase=%s",
        preflight_report["renderer"],
        preflight_report["assets_dir"],
        preflight_report["fonts_dir"],
        preflight_report["fonts_source"],
        preflight_report["supabase"],
    )
    while True:
        job = claim_next_job()
        if not job:
            time.sleep(settings.poll_interval_seconds)
            continue
        try:
            process_job(job)
        except Exception as exc:
            classified = classify_structuring_error(exc)
            log.error("job failed request_id=%s category=%s", job.get("id"), classified["category"])
            fail_job(job, exc, "failed")

if __name__ == "__main__":
    main()
