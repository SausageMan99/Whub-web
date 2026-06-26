from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .packing import build_layout_packing_options, assert_packing_preserves_experience_content
from .retry import is_safe_layout_retry_report, assert_layout_retry_preserves_content
from .variants import (
    LayoutVariantAttempt,
    LayoutVariantSelection,
    evaluate_layout_variant,
    run_bounded_layout_variant_loop,
    select_best_layout_variant,
)

__all__ = [
    "run_layout",
    "run_bounded_layout_variant_loop",
    "build_layout_packing_options",
    "assert_packing_preserves_experience_content",
    "is_safe_layout_retry_report",
    "assert_layout_retry_preserves_content",
    "LayoutVariantAttempt",
    "LayoutVariantSelection",
    "evaluate_layout_variant",
    "select_best_layout_variant",
]


@dataclass(frozen=True)
class LayoutResult:
    """Result of layout rendering with QA."""
    pdf: Path
    qa_report: dict[str, Any]
    layout_options: dict[str, Any]
    attempts_count: int
    selected_variant: str


def run_layout(
    *,
    structured: dict[str, Any],
    workdir: Path,
    render_pdf: Callable[..., Path],
    run_qa: Callable[..., dict[str, Any]],
    forbidden_names: list[str] | None = None,
    source_text: str | None = None,
    base_options: dict[str, Any] | None = None,
    max_attempts: int = 2,
) -> LayoutResult:
    """
    Render/QA a bounded set of layout variants and return the best safe result.

    Single entry point that handles:
    - Initial packing options (if not provided in base_options)
    - Base render + QA
    - At most one deterministic retry for pure layout issues
    - Selection by human-taste score

    Returns the best LayoutResult with metadata for event emission.
    """
    options: dict[str, Any] = deepcopy(base_options) if isinstance(base_options, dict) else {}

    # If no renderer-hint options provided, compute packing options from structured data
    if not any(key in options for key in ("force_experiences_new_page", "force_page_break_before_experience_indexes", "allow_grouping", "density_profile")):
        options = build_layout_packing_options(structured)

    forbidden = forbidden_names or []

    attempts: list[LayoutVariantAttempt] = []
    seen_options: set[tuple[tuple[str, str], ...]] = set()

    def _stable_key(opts: dict[str, Any]) -> tuple[tuple[str, str], ...]:
        return tuple(sorted((str(k), repr(v)) for k, v in opts.items()))

    def _try_variant(name: str, opts: dict[str, Any], output_name: str) -> None:
        if len(attempts) >= max_attempts:
            return
        key = _stable_key(opts)
        if key in seen_options:
            return
        seen_options.add(key)
        attempts.append(
            evaluate_layout_variant(
                name=name,
                structured=structured,
                workdir=workdir,
                layout_options=opts,
                render_pdf=render_pdf,
                run_qa=run_qa,
                forbidden_names=forbidden,
                source_text=source_text,
                output_name=output_name,
            )
        )

    # Base render
    _try_variant("base", deepcopy(options), "output.pdf")

    # Deterministic retry on pure layout issues
    if attempts:
        first = attempts[0]
        if is_safe_layout_retry_report(first.qa_report) and len(attempts) < max_attempts:
            from .intelligence import build_layout_retry_options
            retry_options = build_layout_retry_options(options, first.qa_report)
            _try_variant("layout_retry", retry_options, "output_layout_retry.pdf")

    selection = select_best_layout_variant(attempts)

    if selection.hard_failure is not None:
        hard_report = dict(selection.hard_failure.qa_report or {})
        if _can_return_layout_hard_failure_as_draft(hard_report):
            hard_report["_draft_ready_for_layout_hard_failure"] = True
            return LayoutResult(
                pdf=selection.hard_failure.pdf,
                qa_report=hard_report,
                layout_options=selection.hard_failure.layout_options,
                attempts_count=len(attempts),
                selected_variant=selection.hard_failure.name,
            )
        raise RuntimeError(f"Layout hard failure: {selection.hard_failure.qa_report}")

    if selection.selected is None:
        raise RuntimeError("No layout variant produced a QA report")

    return LayoutResult(
        pdf=selection.selected_pdf,
        qa_report=selection.selected_report,
        layout_options=selection.selected.layout_options,
        attempts_count=len(attempts),
        selected_variant=selection.selected.name,
    )


def _can_return_layout_hard_failure_as_draft(report: dict[str, Any]) -> bool:
    """Allow Telegram-like draft delivery for pure layout/taste failures only."""
    if not isinstance(report, dict):
        return False
    hard_safety_failed = (
        bool(report.get("contact_hits"))
        or bool(report.get("bad_glyphs"))
        or bool(report.get("content_integrity_issues"))
        or bool(report.get("text_overflow_hits"))
        or not report.get("has_logo")
        or not report.get("has_watermark")
        or int(report.get("pages") or 0) <= 0
    )
    if hard_safety_failed:
        return False
    return bool(report.get("layout_issues") or report.get("human_taste"))
