import logging
import time
import re
from time import perf_counter
from pathlib import Path
from datetime import datetime, timezone
import shutil
from collections.abc import Callable
from typing import Any, cast
from .config import settings
from .supabase_client import client
from .events import emit_event
from .extraction import download_source, extract_pdf_text
from .structuring import (
    build_whub_json,
    assert_no_contact_in_json,
    sanitize_contact_in_json,
    enforce_client_first_name,
    normalize_candidate_first_name,
    infer_forbidden_candidate_identity_terms,
    classify_structuring_error,
    RETRYABLE_STRUCTURING_CATEGORIES,
    StructuringError,
    ContactLeakDiagnostic,
    _infer_first_name_from_source,
    _CandidateFirstNameInferenceError,
)
from .revisions import classify_revision_intent
from .rendering import render_pdf
from .qa import run_qa, classify_qa_report
from .storage import save_version
from .layout import build_layout_packing_options, run_layout
from .layout.comment_hints import build_layout_revision_options, mentions_move_from_last_page
from .layout.revision_verification import verify_layout_revision_improved
from .preflight import run_startup_preflight
from .source_sanitizer import sanitize_source_text, SourceSanitizationError
from .quality_report import (
    QualityReportBuilder,
    classify_source_profile,
    should_require_human_review,
)
from .content_blocks import BlockType, ContentBlock, SourceDocument
from .content_preserving_pipeline import render_best_content_preserving_variant
from .section_classifier import classify_sections
from .source_coverage import compare_required_block_coverage
from .block_sanitizer import sanitize_document
from .visual_skills_extraction import apply_visual_skills_override, extract_visual_skills
from .revisions import requests_skills_revision

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO), format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("whub-cv-worker")

VISUAL_SKILLS_MIN_CONFIDENCE = 0.75


def _apply_source_wins_post_structuring(structured: dict[str, Any], source: Path) -> dict[str, Any]:
    visual_skills = extract_visual_skills(source)
    return apply_visual_skills_override(
        structured,
        visual_skills,
        min_confidence=VISUAL_SKILLS_MIN_CONFIDENCE,
    )


def _text_blocks_to_source_document(text: str, *, default_type: BlockType = "other") -> SourceDocument:
    """Convert a sanitized text blob to a ``SourceDocument``.

    This is the simplest possible blockifier for the content-preserving
    shadow/active path: one block per non-empty paragraph. Real production
    wiring should eventually use ``extract_visual_text_blocks(pdf_path)``
    with the actual PDF; this helper exists so the integration can be
    tested end-to-end without a real PDF and without coupling the new
    pipeline to the existing structuring path.
    """
    paragraphs = [chunk.strip() for chunk in re.split(r"\n\s*\n", text or "") if chunk.strip()]
    if not paragraphs:
        return SourceDocument(blocks=[])
    blocks: list[ContentBlock] = []
    for index, paragraph in enumerate(paragraphs, start=1):
        blocks.append(
            ContentBlock.from_text(
                default_type,
                source_order=index,
                page=0,
                text=paragraph,
            )
        )
    return SourceDocument(blocks=blocks)


def _run_content_preserving_shadow(
    request_id: str,
    sanitized_text: str,
    candidate_first_name: str | None,
    workdir: Path,
) -> None:
    """Evaluate the content-preserving pipeline in shadow mode.

    Shadow mode never changes the delivered output, never updates
    ``current_version_id``, and never calls ``save_version``. It only
    emits a redacted ``content_preserving_shadow_evaluated`` event so an
    operator can compare the new pipeline against the existing one.
    Any exception is caught and converted to a redacted
    ``content_preserving_shadow_failed`` event.
    """
    try:
        raw_doc = _text_blocks_to_source_document(sanitized_text)
        sanitized = sanitize_document(
            raw_doc,
            candidate_first_name=candidate_first_name or "",
            forbidden_identity_terms=[],
        )
        classified = classify_sections(sanitized.document)
        out_dir = workdir / "content_preserving_shadow"
        result = render_best_content_preserving_variant(
            classified,
            candidate_first_name=candidate_first_name or "CV",
            output_dir=out_dir,
        )
        emit_event(
            request_id,
            "content_preserving_shadow_evaluated",
            {
                "variant": result.variant,
                "missing_required_blocks_count": len(result.missing_required_blocks),
            },
        )
    except Exception as exc:  # noqa: BLE001 - shadow must never break the main job
        emit_event(
            request_id,
            "content_preserving_shadow_failed",
            {"error_category": "content_preserving_shadow_error"},
        )
        log.warning("content_preserving_shadow failed request_id=%s err=%r", request_id, exc)


def _run_content_preserving_active(
    request_id: str,
    sanitized_text: str,
    candidate_first_name: str | None,
    job: dict,
    workdir: Path,
) -> str:
    """Run the content-preserving pipeline end-to-end and save the version.

    Returns ``"ok"`` on success, ``"failed"`` if the pipeline errors out
    (in which case the job is recorded as failed via ``fail_job``).
    The existing pipeline is NOT called when this returns ``"ok"`` —
    the new pipeline owns the rest of the job.
    """
    try:
        raw_doc = _text_blocks_to_source_document(sanitized_text)
        sanitized = sanitize_document(
            raw_doc,
            candidate_first_name=candidate_first_name or "",
            forbidden_identity_terms=[],
        )
        classified = classify_sections(sanitized.document)
        out_dir = workdir / "content_preserving_active"
        result = render_best_content_preserving_variant(
            classified,
            candidate_first_name=candidate_first_name or "CV",
            output_dir=out_dir,
        )

        structured: dict[str, Any] = {
            "name": candidate_first_name or "CV",
            "formations": [],
            "skills": [],
            "experiences": [
                {
                    "date": "",
                    "role": block.text,
                    "company_highlight": "",
                    "sections": [],
                }
                for block in classified.ordered_blocks()
                if block.required and block.type == "experience"
            ],
            "content_preserving": {
                "variant": result.variant,
                "missing_required_blocks": result.missing_required_blocks,
            },
        }

        qa_report: dict[str, Any] = {
            "pages": 1,
            "has_logo": False,
            "has_watermark": False,
            "layout_issues": [],
            "content_preserving": True,
        }

        has_missing = bool(result.missing_required_blocks)
        request_status = "draft_ready" if has_missing else "ready"
        qa_status = "draft" if has_missing else "passed"

        saved = save_version(
            request_id,
            structured,
            result.final_pdf_path,
            qa_report,
            request_status=request_status,
            qa_status=qa_status,
            owner=job.get("created_by") or settings.worker_name,
        )

        event_payload: dict[str, Any] = {
            "version_id": saved["id"],
            "version_number": saved["version_number"],
            "layout_variant": result.variant,
        }
        if has_missing:
            event_payload["missing_required_blocks"] = result.missing_required_blocks
        emit_event(request_id, request_status, event_payload)
        return "ok"
    except Exception as exc:  # noqa: BLE001 - surface as a clean failed job
        fail_job(job, exc, "failed")
        return "failed"


class CircuitBreaker:
    """Simple circuit breaker for the worker polling path."""

    CLOSED = "closed"
    OPEN = "open"
    HALF_OPEN = "half-open"

    def __init__(
        self,
        failure_threshold: int = 10,
        recovery_timeout: float = 300,
        time_func: Callable[[], float] = time.monotonic,
    ) -> None:
        self.failure_threshold = failure_threshold
        self.recovery_timeout = recovery_timeout
        self.time_func = time_func
        self.state = self.CLOSED
        self.failure_count = 0
        self.opened_at: float | None = None

    def allow_request(self) -> bool:
        if self.state != self.OPEN:
            return True
        if self.opened_at is None:
            self.opened_at = self.time_func()
            return False
        if self.time_func() - self.opened_at >= self.recovery_timeout:
            self.state = self.HALF_OPEN
            return True
        return False

    def record_success(self) -> None:
        self.state = self.CLOSED
        self.failure_count = 0
        self.opened_at = None

    def record_failure(self) -> None:
        if self.state == self.HALF_OPEN:
            self._open()
            return
        self.failure_count += 1
        if self.failure_count >= self.failure_threshold:
            self._open()

    def _open(self) -> None:
        self.state = self.OPEN
        self.opened_at = self.time_func()


def _backoff_delay(attempt: int, base_delay: float, max_delay: float = 300) -> float:
    return min(base_delay * (2 ** (attempt - 1)), max_delay)


def poll_with_backoff(
    claim_func: Callable[[], dict | None] | None = None,
    process_func: Callable[[dict], None] | None = None,
    sleep_func: Callable[[float], None] = time.sleep,
    base_delay: float | None = None,
    breaker: CircuitBreaker | None = None,
    max_delay: float = 300,
    reap_func: Callable[[], int] | None = None,
    reap_interval_seconds: float | None = None,
) -> None:
    """Poll for CV jobs with exponential backoff and circuit-breaker protection.

    Consecutive errors while claiming work are backed off exponentially from
    ``base_delay`` and capped at ``max_delay``. After 10 consecutive claim
    failures by default, the circuit opens and skips claim attempts until the
    recovery timeout elapses. When ``reap_func`` is provided, it is invoked
    every ``reap_interval_seconds`` to recover stale ``processing`` rows.
    """
    claim = claim_next_job if claim_func is None else claim_func
    process = process_job if process_func is None else process_func
    poll_delay = settings.poll_interval_seconds if base_delay is None else base_delay
    circuit_breaker = breaker or CircuitBreaker(recovery_timeout=max_delay)
    reap_interval = (
        settings.reap_interval_seconds if reap_interval_seconds is None else reap_interval_seconds
    )
    last_reap = time.monotonic()
    error_attempt = 0

    while True:
        if reap_func is not None and (time.monotonic() - last_reap) >= reap_interval:
            try:
                reap_func()
            except Exception:
                log.exception("stale reaper run failed")
            last_reap = time.monotonic()
        if not circuit_breaker.allow_request():
            log.warning("poll circuit breaker open; sleeping %.0fs", circuit_breaker.recovery_timeout)
            sleep_func(circuit_breaker.recovery_timeout)
            continue

        try:
            job = claim()
        except Exception:
            error_attempt += 1
            circuit_breaker.record_failure()
            delay = _backoff_delay(error_attempt, poll_delay, max_delay)
            log.exception(
                "poll failed attempt=%s circuit_state=%s; sleeping %.0fs",
                error_attempt,
                circuit_breaker.state,
                delay,
            )
            sleep_func(delay)
            continue

        circuit_breaker.record_success()
        error_attempt = 0
        if not job:
            sleep_func(poll_delay)
            continue
        try:
            process(job)
        except Exception as exc:
            classified = classify_structuring_error(exc)
            log.error("job failed request_id=%s category=%s", job.get("id"), classified["category"])
            try:
                handle_job_failure(job, exc)
            except Exception:
                log.exception("job failure handling crashed request_id=%s", job.get("id"))

def claim_next_job() -> dict | None:
    res = client.rpc("claim_next_cv_request", {"worker_name": settings.worker_name}).execute()
    return res.data[0] if res.data else None


def _coerce_utc(value: Any) -> datetime | None:
    """Return an aware UTC datetime for psycopg2 / REST timestamp values."""
    if isinstance(value, datetime):
        return value if value.tzinfo else value.replace(tzinfo=timezone.utc)
    if isinstance(value, str):
        try:
            parsed = datetime.fromisoformat(value.replace("Z", "+00:00"))
        except ValueError:
            return None
        return parsed if parsed.tzinfo else parsed.replace(tzinfo=timezone.utc)
    return None


def reap_stale_processing_jobs(
    stale_minutes: int | None = None,
    now: datetime | None = None,
) -> int:
    """Recover jobs stuck in ``processing`` after a crash or a lost worker.

    The claim RPC only picks up ``submitted``/``revision_requested`` rows, so
    a worker that dies mid-job — or a request deleted while in flight — leaves
    its row in ``processing`` forever: invisible to the queue and blocking the
    portal (incident "Quincy", stuck since 2026-07-23). Rows whose lock is
    older than ``stale_lock_minutes`` are requeued while retry budget remains,
    and failed honestly once exhausted. Runs on startup and periodically.
    """
    stale_after = settings.stale_lock_minutes if stale_minutes is None else stale_minutes
    current = now or datetime.now(timezone.utc)
    try:
        res = (
            client.table("cv_requests")
            .select("id,worker_attempts,worker_locked_at,updated_at,started_at")
            .eq("status", "processing")
            .execute()
        )
    except Exception:
        log.exception("stale reaper: processing scan failed")
        return 0
    reaped = 0
    for row in res.data or []:
        locked = (
            _coerce_utc(row.get("worker_locked_at"))
            or _coerce_utc(row.get("updated_at"))
            or _coerce_utc(row.get("started_at"))
        )
        if locked is None:
            continue
        age_minutes = (current - locked).total_seconds() / 60.0
        if age_minutes < stale_after:
            continue
        request_id = str(row.get("id") or "")
        attempts = int(row.get("worker_attempts") or 0)
        requeue = attempts < settings.max_attempts
        try:
            client.table("cv_requests").update({
                "status": "submitted" if requeue else "failed",
                "worker_locked_at": None,
                "worker_locked_by": None,
                "last_error": (
                    f"Reprise automatique: verrou de traitement expiré (>{stale_after:g} min). "
                    + ("Nouvelle tentative planifiée." if requeue else "Tentatives épuisées.")
                ),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", request_id).execute()
        except Exception:
            log.exception("stale reaper: repair failed request_id=%s", request_id)
            continue
        try:
            emit_event(
                request_id,
                "job_requeued_after_stale_lock" if requeue else "job_failed_after_stale_lock",
                {"attempts": attempts, "age_minutes": round(age_minutes, 1)},
            )
        except Exception:
            log.exception("stale reaper: event failed request_id=%s", request_id)
        reaped += 1
        log.warning(
            "stale reaper: request_id=%s attempts=%s age=%.0fmin -> %s",
            request_id,
            attempts,
            age_minutes,
            "submitted" if requeue else "failed",
        )
    return reaped


def fail_job(job: dict, error: str | Exception, status: str = "failed") -> None:
    """Persist a terminal failure state for ``job``.

    Must never raise: this is the last stop of the failure path. A raising
    finalization (e.g. FK violation when the request row was deleted while the
    job was in flight) kills the whole worker process — systemd then restarts
    it mid-queue and in-flight state is lost (incident 2026-09-21 14:42 UTC).
    """
    request_id = str(job.get("id") or "")
    try:
        classified = classify_structuring_error(error)
    except Exception:  # pragma: no cover - defensive fallback
        log.exception("fail_job: classification failed request_id=%s", request_id)
        classified = {
            "category": "transient_model_failure",
            "message": "Échec du traitement de la demande.",
        }
    safe_error = classified["message"][:500]
    try:
        client.table("cv_requests").update({
            "status": status,
            "last_error": safe_error,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }).eq("id", request_id).execute()
    except Exception:
        log.exception("fail_job: state update failed request_id=%s", request_id)

    event_payload: dict[str, Any] = {"error": safe_error, "error_category": classified["category"]}
    if classified["category"] == "contact_leak":
        diagnostic = getattr(error, "contact_diagnostic", None)
        if isinstance(diagnostic, ContactLeakDiagnostic) and diagnostic.categories:
            event_payload["contact_categories"] = list(diagnostic.categories)
            event_payload["contact_paths"] = list(diagnostic.paths) if diagnostic.paths else []
    # Extract safe fidelity issue codes from the error message
    error_str = str(error)
    fidelity_match = re.search(r"fidelity_issues=\[([^\]]+)\]", error_str)
    if fidelity_match:
        codes = [c.strip() for c in fidelity_match.group(1).split(",") if c.strip()]
        event_payload["fidelity_issues"] = codes
    hard_match = re.search(r"hard_count=(\d+)", error_str)
    soft_match = re.search(r"soft_count=(\d+)", error_str)
    if hard_match and soft_match:
        event_payload["fidelity_hard_count"] = int(hard_match.group(1))
        event_payload["fidelity_soft_count"] = int(soft_match.group(1))
    try:
        emit_event(request_id, status, event_payload)
    except Exception:
        log.exception("fail_job: event emit failed request_id=%s", request_id)


def handle_job_failure(job: dict, exc: Exception | str) -> None:
    """Retry transient model failures a bounded number of times, then fail.

    The claim RPC only picks up ``submitted``/``revision_requested`` rows and
    stops claiming once ``worker_attempts >= settings.max_attempts``; moving a
    failed-once job back to ``submitted`` below is what schedules its retry.
    Deterministic failures (fidelity, contact, sanitization) go straight to
    ``fail_job``.
    """
    request_id = str(job.get("id") or "")
    classified = classify_structuring_error(exc)
    category = classified["category"]
    attempts = int(job.get("worker_attempts") or 0)
    if category in RETRYABLE_STRUCTURING_CATEGORIES and attempts < settings.max_attempts:
        try:
            client.table("cv_requests").update({
                "status": "submitted",
                "worker_locked_at": None,
                "worker_locked_by": None,
                "last_error": (
                    f"{classified['message']} — tentative {attempts}/{settings.max_attempts}"
                    " échouée, nouvelle tentative planifiée."
                ),
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", request_id).execute()
        except Exception:
            log.exception("retry scheduling failed request_id=%s; failing instead", request_id)
            fail_job(job, exc, "failed")
            return
        try:
            emit_event(
                request_id,
                "job_retry_scheduled",
                {
                    "category": category,
                    "attempt": attempts,
                    "max_attempts": settings.max_attempts,
                },
            )
        except Exception:
            log.exception("retry event failed request_id=%s", request_id)
        log.warning(
            "job retry scheduled request_id=%s category=%s attempt=%s/%s",
            request_id,
            category,
            attempts,
            settings.max_attempts,
        )
        return
    fail_job(job, exc, "failed")


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


def _build_source_quality_payload(text: str, raw_chars: int, sanitized_chars: int) -> dict[str, Any]:
    """Build a redacted ``quality_source_profiled`` event payload.

    The payload only carries counts, scores, and the source profile name. It
    must never embed the source text or any contact-like value.
    """
    profile = classify_source_profile(text)
    builder = QualityReportBuilder(request_id="event_payload")
    builder.set_source_profile(profile["profile"])
    builder.add_metric("raw_chars", raw_chars)
    builder.add_metric("sanitized_chars", sanitized_chars)
    builder.add_metric("line_count", profile["line_count"])
    builder.add_metric("mission_markers", profile["mission_markers"])
    builder.add_metric("ats_markers", profile["ats_markers"])
    builder.add_metric("short_line_ratio", profile["short_line_ratio"])
    extraction_score = (
        35
        if profile["profile"] == "scanned"
        else 72
        if profile["profile"] in {"two_column", "risky"}
        else 88
    )
    builder.add_score("extraction", extraction_score)
    report = builder.to_dict(stage="extraction")
    return {
        "source_profile": report["source_profile"],
        "scores": report["scores"],
        "metrics": report["metrics"],
        "hard_blockers": report["hard_blockers"],
        "soft_warnings": report["soft_warnings"],
    }


def _attach_final_quality_report(
    *,
    qa_report: dict[str, Any],
    request_id: str,
    source_profile: str,
    final_qa_status: str,
    layout_warnings: list[dict[str, Any]],
    attempts_count: int,
    total_duration_seconds: float,
    fidelity_soft_warnings: list[Any] | None = None,
) -> dict[str, Any]:
    """Return ``qa_report`` enriched with a redacted ``quality_report`` block.

    The block is the canonical quality summary read by the web cockpit and by
    any future analytics. It must never contain raw contact values; the
    builder enforces that contract.
    """
    builder = QualityReportBuilder(request_id=request_id)
    builder.set_source_profile(source_profile)
    builder.add_metric("pages", int(qa_report.get("pages") or 0))
    builder.add_metric("attempts_count", attempts_count)
    builder.add_metric("total_duration_seconds", round(float(total_duration_seconds), 2))
    builder.add_metric("final_qa_status", final_qa_status)

    layout_score = max(0, 100 - (len(layout_warnings) * 12))
    builder.add_score("layout", layout_score)
    builder.add_score("fidelity", 82 if fidelity_soft_warnings else 100)
    overall = min(builder.scores.get("layout", 0), builder.scores.get("fidelity", 0))
    builder.add_score("overall", overall)

    if final_qa_status == "failed":
        builder.add_hard_blocker("qa_failed", stage="qa")

    for issue in layout_warnings:
        if not isinstance(issue, dict):
            continue
        code = str(issue.get("code") or "layout_warning")
        page = issue.get("page")
        extra = {"page": int(page)} if isinstance(page, int) else {}
        builder.add_soft_warning(code, stage="layout", **extra)

    for warning in fidelity_soft_warnings or []:
        if isinstance(warning, dict):
            code = str(warning.get("code") or "source_fidelity_warning")
            builder.add_soft_warning(code, stage="fidelity")
        else:
            builder.add_soft_warning(str(warning), stage="fidelity")

    updated = dict(qa_report)
    updated["quality_report"] = builder.to_dict(stage="final")
    return updated


def _build_safe_sanitization_event_payload(report) -> dict:
    """Return a sanitization event payload with counts only, never raw values."""
    return {
        "raw_chars": int(getattr(report, "raw_chars", 0)),
        "sanitized_chars": int(getattr(report, "sanitized_chars", 0)),
        "removed_email_count": int(getattr(report, "removed_email_count", 0)),
        "removed_phone_count": int(getattr(report, "removed_phone_count", 0)),
        "removed_url_count": int(getattr(report, "removed_url_count", 0)),
        "removed_linkedin_count": int(getattr(report, "removed_linkedin_count", 0)),
        "removed_github_profile_count": int(getattr(report, "removed_github_profile_count", 0)),
        "removed_address_line_count": int(getattr(report, "removed_address_line_count", 0)),
        "removed_contact_label_line_count": int(getattr(report, "removed_contact_label_line_count", 0)),
        "removed_hellowork_line_count": int(getattr(report, "removed_hellowork_line_count", 0)),
        "removed_empty_or_boilerplate_line_count": int(getattr(report, "removed_empty_or_boilerplate_line_count", 0)),
        "warnings": list(getattr(report, "warnings", ()) or ()),
    }


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


def _maybe_reuse_layout_only_structured_json(
    *,
    client,
    request_id: str,
    current_version_id: str | None,
    revision_comments: list[dict],
    effective_first_name: str | None,
    timings: dict,
    structured_sink: dict,
) -> bool:
    """Returns True if layout_only routing was applied."""
    if not current_version_id or not revision_comments:
        structured_sink.setdefault("layout_only_active", False)
        return False

    from .revisions import classify_revision_intent
    from .layout.comment_hints import build_layout_revision_options, mentions_move_from_last_page

    layout_revision_candidates: list[dict] = []
    for comment in revision_comments:
        body = str(comment.get("body") or "")
        intent = classify_revision_intent(body)
        if intent.kind != "layout_only":
            continue
        layout_revision_candidates.append(comment)

    if not layout_revision_candidates:
        structured_sink.setdefault("layout_only_active", False)
        return False

    stage_start = perf_counter()
    version_res = (
        client.table("cv_versions")
        .select("id,structured_json,qa_report,version_number,qa_status")
        .eq("id", current_version_id)
        .execute()
    )
    timings["load_layout_only_version"] = perf_counter() - stage_start

    if not version_res.data:
        structured_sink.setdefault("layout_only_active", False)
        return False

    row = version_res.data[0]
    structured_json = row.get("structured_json")
    if not structured_json:
        structured_sink.setdefault("layout_only_active", False)
        return False

    structured_sink["structured"] = structured_json
    structured_sink["layout_only_active"] = True
    structured_sink["prev_qa"] = row.get("qa_report") or {}
    structured_sink["revision_comments"] = revision_comments
    emit_event(
        request_id,
        "layout_revision_detected",
        {
            "comments_count": len(layout_revision_candidates),
            "from_version_id": current_version_id,
            "intent": "layout_only",
            "routing": "renderer_only",
        },
    )
    emit_event(
        request_id,
        "layout_revision_reused_structured_json",
        {
            "version_id": row.get("id"),
            "version_number": row.get("version_number"),
        },
    )
    return True


def _mark_qa_report_draft_override(qa_report: dict, reason: str) -> dict:
    """Record that a passing QA report was downgraded to draft by the worker.

    save_version refuses draft_ready + qa_report.passed=true, so a downgrade
    must flip ``passed`` and say why instead of silently contradicting QA.
    """
    return {**qa_report, "passed": False, "draft_override_reason": reason}


def process_job(job: dict) -> None:
    total_start = perf_counter()
    timings: dict[str, float] = {}
    request_id = job["id"]
    workdir = Path(settings.tmp_dir) / request_id
    if workdir.exists():
        shutil.rmtree(workdir)
    workdir.mkdir(parents=True, exist_ok=True)
    try:
        emit_event(request_id, "worker_claimed")

        stage_start = perf_counter()
        source = download_source(job, workdir)
        timings["download_source"] = perf_counter() - stage_start

        stage_start = perf_counter()
        text = extract_pdf_text(source)
        timings["extract_text"] = perf_counter() - stage_start
        emit_event(request_id, "extraction_done", {"chars": len(text)})

        # Short-circuit to ``needs_human_review`` when the raw extraction is
        # too short or too uncertain to safely auto-generate. We check BEFORE
        # sanitization so that an almost-empty source never explodes the
        # sanitizer with a low-quality failure and surfaces a clearer
        # ``needs_human_review`` status instead.
        raw_profile = classify_source_profile(text)
        if should_require_human_review(raw_profile):
            source_profile = raw_profile["profile"]
            client.table("cv_requests").update({
                "status": "needs_human_review",
                "last_error": "Extraction peu fiable : validation humaine requise avant génération.",
                "updated_at": datetime.now(timezone.utc).isoformat(),
            }).eq("id", request_id).execute()
            source_profile_payload = _build_source_quality_payload(
                text, raw_chars=len(text), sanitized_chars=0
            )
            emit_event(request_id, "quality_source_profiled", source_profile_payload)
            emit_event(
                request_id,
                "needs_human_review",
                {"source_profile": source_profile, "reason": "extraction_low_confidence"},
            )
            return

        try:
            sanitization = sanitize_source_text(text, job.get("candidate_first_name"))
        except SourceSanitizationError as exc:
            fail_job(job, exc, "failed")
            return
        sanitized_text = sanitization.text
        emit_event(request_id, "source_sanitized", _build_safe_sanitization_event_payload(sanitization.report))
        source_profile_payload = _build_source_quality_payload(
            text, raw_chars=len(text), sanitized_chars=len(sanitized_text)
        )
        source_profile = source_profile_payload["source_profile"]
        emit_event(request_id, "quality_source_profiled", source_profile_payload)

        # Active content-preserving pipeline. Off by default. When on, the
        # new pipeline owns the rest of the job and the existing pipeline is
        # NOT called.
        if settings.whub_content_preserving_pipeline:
            active_status = _run_content_preserving_active(
                request_id,
                sanitized_text,
                job.get("candidate_first_name"),
                job,
                workdir,
            )
            return

        # Shadow evaluation of the content-preserving pipeline. Never changes
        # the delivered output. Off by default.
        if settings.whub_content_preserving_shadow:
            _run_content_preserving_shadow(
                request_id,
                sanitized_text,
                job.get("candidate_first_name"),
                workdir,
            )

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
        revision_comments = [c for c in comments_for_prompt if c.get("comment_type") == "revision"]
        effective_first_name = job.get("candidate_first_name") or None
        if not effective_first_name:
            try:
                inferred_first, _ = _infer_first_name_from_source(text)
                if inferred_first:
                    effective_first_name = inferred_first
            except _CandidateFirstNameInferenceError:
                pass
            if not effective_first_name:
                fail_job(
                    job,
                    StructuringError("missing_candidate_first_name: no Prénom NOM pattern inferable from source"),
                    "failed",
                )
                return

        layout_only: dict[str, Any] = {
            "structured": None,
            "layout_only_active": False,
            "prev_qa": {},
            "revision_comments": [],
        }
        reused = _maybe_reuse_layout_only_structured_json(
            client=client,
            request_id=request_id,
            current_version_id=current_version_id,
            revision_comments=revision_comments,
            effective_first_name=effective_first_name,
            timings=timings,
            structured_sink=layout_only,
        )
        if reused:
            structured = layout_only["structured"]
        else:
            structured = build_whub_json(
                sanitized_text, job.get("instructions") or "", comments_for_prompt, effective_first_name
            )
            # A revision comment on the skills is answered by the model: the
            # source skills read from the PDF styles must not overwrite it.
            if not requests_skills_revision(comments_for_prompt):
                structured = _apply_source_wins_post_structuring(structured, source)
        enforce_client_first_name(structured, effective_first_name)
        # Soft fidelity warnings: extract and remove from data so they don't pollute the render
        fidelity_soft_warnings = structured.pop("_fidelity_soft_warnings", None)
        timings["hermes_structuring"] = perf_counter() - stage_start

        stage_start = perf_counter()
        structured = sanitize_contact_in_json(structured)
        assert_no_contact_in_json(structured)
        layout_options = build_layout_packing_options(structured)
        forbidden_names = forbidden_candidate_name_parts(job.get("candidate_first_name"), text)
        try:
            layout_result = run_layout(
                structured=structured,
                workdir=workdir,
                render_pdf=render_pdf,
                run_qa=run_qa,
                forbidden_names=forbidden_names,
                source_text=sanitized_text,
                base_options=layout_options,
            )
        except RuntimeError as exc:
            fail_job(job, str(exc), "qa_failed")
            return
        timings["render_pdf_qa_layout_variants"] = perf_counter() - stage_start
        pdf = layout_result.pdf
        qa_report = layout_result.qa_report
        if layout_result.attempts_count > 1:
            emit_event(
                request_id,
                "layout_variant_selected",
                {
                    "selected": layout_result.selected_variant,
                    "attempts_count": layout_result.attempts_count,
                },
            )

        final_qa_status, layout_warnings = classify_qa_report(qa_report)
        draft_override_reason: str | None = None
        if final_qa_status == "failed":
            fail_job(job, str(qa_report), "qa_failed")
            return
        if layout_only.get("layout_only_active"):
            verify_warnings: list = []
            try:
                verify_ok, verify_warnings = verify_layout_revision_improved(
                    previous_qa_report=layout_only.get("prev_qa") or {},
                    new_qa_report=qa_report,
                    comments=[c.get("body") or "" for c in (layout_only.get("revision_comments") or [])],
                )
            except Exception as exc:  # noqa: BLE001
                log.warning("layout_revision_verification_failed request_id=%s err=%r", request_id, exc)
                verify_ok = False
                verify_warnings = [{"code": "verification_error", "message": "Vérification de la révision impossible."}]
            if not verify_ok:
                if final_qa_status == "passed":
                    final_qa_status = "draft"
                    draft_override_reason = "layout_revision_unverified"
                layout_warnings = [*layout_warnings, *verify_warnings]
        # If we have fidelity soft warnings, force draft_ready even if QA passed
        if fidelity_soft_warnings and final_qa_status == "passed":
            final_qa_status = "draft"
            draft_override_reason = "fidelity_soft_warnings"
        if draft_override_reason:
            qa_report = _mark_qa_report_draft_override(qa_report, draft_override_reason)
        request_status = "draft_ready" if final_qa_status == "draft" else "ready"
        version_qa_status = "draft" if final_qa_status == "draft" else "passed"

        # Compute total duration before save_version so the final quality_report
        # is persisted alongside the version row instead of added afterwards.
        total_duration_seconds = perf_counter() - total_start
        qa_report = _attach_final_quality_report(
            qa_report=qa_report,
            request_id=request_id,
            source_profile=source_profile,
            final_qa_status=final_qa_status,
            layout_warnings=layout_warnings,
            attempts_count=layout_result.attempts_count,
            total_duration_seconds=total_duration_seconds,
            fidelity_soft_warnings=fidelity_soft_warnings,
        )

        stage_start = perf_counter()
        saved_version = save_version(
            request_id,
            structured,
            pdf,
            qa_report,
            request_status=request_status,
            qa_status=version_qa_status,
            owner=job.get("created_by") or settings.worker_name,
        )
        client.table("cv_comments").update({"resolved": True}).eq("request_id", request_id).eq("comment_type", "revision").execute()
        event_payload = {"version_id": saved_version["id"], "version_number": saved_version["version_number"]}
        if request_status == "draft_ready" or layout_warnings:
            # A ready CV can carry advisory layout warnings (qa.ADVISORY_LAYOUT_CODES).
            event_payload["layout_warnings"] = layout_warnings
        if fidelity_soft_warnings:
            event_payload["fidelity_warnings"] = fidelity_soft_warnings
        emit_event(request_id, request_status, event_payload)
        timings["upload_and_finalize"] = perf_counter() - stage_start
        timings["total"] = total_duration_seconds
        log.info("job timings request_id=%s %s", request_id, " ".join(f"{key}={value:.2f}s" for key, value in timings.items()))
    finally:
        if workdir.exists():
            shutil.rmtree(workdir, ignore_errors=True)

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
    recovered = reap_stale_processing_jobs()
    if recovered:
        log.warning("startup stale reaper: %s job(s) recovered", recovered)
    poll_with_backoff(reap_func=reap_stale_processing_jobs)

if __name__ == "__main__":
    main()
