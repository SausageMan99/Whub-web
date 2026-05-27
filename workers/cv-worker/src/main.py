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
from .structuring import build_whub_json, assert_no_contact_in_json
from .rendering import render_pdf
from .qa import run_qa, QAError
from .storage import next_version_number, save_success

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
    timings["hermes_structuring"] = perf_counter() - stage_start

    stage_start = perf_counter()
    assert_no_contact_in_json(structured)
    version_number = next_version_number(request_id)
    pdf = render_pdf(structured, workdir)
    timings["render_pdf"] = perf_counter() - stage_start

    try:
        stage_start = perf_counter()
        qa_report = run_qa(pdf, forbidden_names=[])
        timings["qa"] = perf_counter() - stage_start
    except QAError as e:
        fail_job(job, str(e.report), "qa_failed")
        return

    stage_start = perf_counter()
    version_id = save_success(request_id, version_number, structured, pdf, qa_report)
    client.table("cv_comments").update({"resolved": True}).eq("request_id", request_id).eq("comment_type", "revision").execute()
    emit_event(request_id, "ready", {"version_id": version_id, "version_number": version_number})
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
