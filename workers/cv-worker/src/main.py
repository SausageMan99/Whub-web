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
    enforce_client_first_name,
    normalize_candidate_first_name,
    infer_forbidden_candidate_identity_terms,
    classify_structuring_error,
    StructuringError,
    ContactLeakDiagnostic,
    _infer_first_name_from_source,
    _CandidateFirstNameInferenceError,
)
from .rendering import render_pdf
from .qa import run_qa, classify_qa_report
from .storage import save_version
from .layout import build_layout_packing_options, run_layout
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

logging.basicConfig(level=getattr(logging, settings.log_level.upper(), logging.INFO), format="%(asctime)s %(levelname)s %(message)s")
log = logging.getLogger("whub-cv-worker")


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
) -> None:
    """Poll for CV jobs with exponential backoff and circuit-breaker protection.

    Consecutive errors while claiming work are backed off exponentially from
    ``base_delay`` and capped at ``max_delay``. After 10 consecutive claim
    failures by default, the circuit opens and skips claim attempts until the
    recovery timeout elapses.
    """
    claim = claim_next_job if claim_func is None else claim_func
    process = process_job if process_func is None else process_func
    poll_delay = settings.poll_interval_seconds if base_delay is None else base_delay
    circuit_breaker = breaker or CircuitBreaker(recovery_timeout=max_delay)
    error_attempt = 0

    while True:
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
            fail_job(job, exc, "failed")

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
    emit_event(job["id"], status, event_payload)


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
    fidelity_soft_warnings: list[str] | None = None,
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
        structured = build_whub_json(sanitized_text, job.get("instructions") or "", comments_for_prompt, effective_first_name)
        enforce_client_first_name(structured, effective_first_name)
        # Soft fidelity warnings: extract and remove from data so they don't pollute the render
        fidelity_soft_warnings = structured.pop("_fidelity_soft_warnings", None)
        timings["hermes_structuring"] = perf_counter() - stage_start

        stage_start = perf_counter()
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
        if final_qa_status == "failed":
            fail_job(job, str(qa_report), "qa_failed")
            return
        # If we have fidelity soft warnings, force draft_ready even if QA passed
        if fidelity_soft_warnings and final_qa_status == "passed":
            final_qa_status = "draft"
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
        if request_status == "draft_ready":
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
    poll_with_backoff()

if __name__ == "__main__":
    main()
