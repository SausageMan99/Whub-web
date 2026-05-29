import logging
import time
from time import perf_counter
from pathlib import Path
from datetime import datetime, timezone
import shutil
from .config import settings
from .supabase_client import client
from .events import emit_event
from .extraction import download_source, extract_pdf_text
from .structuring import build_whub_json, assert_no_contact_in_json, enforce_client_first_name, normalize_candidate_first_name, infer_forbidden_candidate_identity_terms
from .rendering import render_pdf
from .qa import run_qa, QAError, classify_qa_report
from .storage import next_version_number, save_version
from .layout_retry import is_safe_layout_retry_report
from .layout_packing import build_layout_packing_options

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO), format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("whub-cv-worker")

def claim_next_job() -> dict | None:
    res = client.rpc("claim_next_cv_request", {"worker_name": settings.worker_name}).execute()
    return res.data[0] if res.data else None

def fail_job(job: dict, error: str, status: str = "failed") -> None:
    safe_error = error[:500]
    client.table("cv_requests").update({
        "status": status,
        "last_error": safe_error,
        "updated_at": datetime.now(timezone.utc).isoformat(),
    }).eq("id", job["id"]).execute()
    emit_event(job["id"], status, {"error": safe_error})


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

    stage_start = perf_counter()
    structured = build_whub_json(text, job.get("instructions") or "", comments_res.data or [], job.get("candidate_first_name"))
    enforce_client_first_name(structured, job.get("candidate_first_name"))
    timings["hermes_structuring"] = perf_counter() - stage_start

    stage_start = perf_counter()
    assert_no_contact_in_json(structured)
    version_number = next_version_number(request_id)
    layout_options = build_layout_packing_options(structured)
    pdf = render_pdf(structured, workdir, layout_options=layout_options)
    timings["render_pdf"] = perf_counter() - stage_start

    forbidden_names = forbidden_candidate_name_parts(job.get("candidate_first_name"), text)
    try:
        stage_start = perf_counter()
        qa_report = run_qa(pdf, forbidden_names=forbidden_names, source_text=text, structured_data=structured)
        timings["qa"] = perf_counter() - stage_start
    except QAError as e:
        qa_status, layout_warnings = classify_qa_report(e.report)
        if qa_status == "failed":
            fail_job(job, str(e.report), "qa_failed")
            return
        qa_report = e.report
        if is_safe_layout_retry_report(e.report):
            emit_event(request_id, "layout_retry", {"reason": "soft_layout_warning", "layout_issues": layout_warnings})
            stage_start = perf_counter()
            pdf = render_pdf(
                structured,
                workdir,
                layout_options={
                    **layout_options,
                    "anti_crowding": True,
                    "force_experiences_new_page": True,
                    "page_dense_char_threshold": 2600,
                    "max_used_ratio": 0.80,
                    "readability_reserve": 170,
                },
                output_name="output_layout_retry.pdf",
            )
            timings["render_pdf_layout_retry"] = perf_counter() - stage_start
            try:
                stage_start = perf_counter()
                qa_report = run_qa(pdf, forbidden_names=forbidden_names, source_text=text, structured_data=structured)
                timings["qa_layout_retry"] = perf_counter() - stage_start
            except QAError as retry_error:
                retry_status, _retry_warnings = classify_qa_report(retry_error.report)
                if retry_status == "failed":
                    fail_job(job, str(retry_error.report), "qa_failed")
                    return
                qa_report = retry_error.report

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
    while True:
        job = claim_next_job()
        if not job:
            time.sleep(settings.poll_interval_seconds)
            continue
        try:
            process_job(job)
        except Exception as exc:
            log.exception("job failed request_id=%s", job.get("id"))
            fail_job(job, str(exc), "failed")

if __name__ == "__main__":
    main()
