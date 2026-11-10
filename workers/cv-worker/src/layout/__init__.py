from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Callable

from .packing import build_layout_packing_options, assert_packing_preserves_experience_content
from .retry import is_safe_layout_retry_report, assert_layout_retry_preserves_content
from .pagination import (
    COMPACT,
    describe_revision_outcome,
    layout_blocking_codes,
    pagination_candidates,
    pagination_cost,
    repair_variant_options,
    report_pages,
    should_try_page_saving,
)
from ..qa_defects import blocking_defects
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
    # Lot 4: what the deterministic retry did ({"initial_blocking": [...],
    # "tried": [...], "repaired": bool, "page_saved": bool}).
    repair: dict[str, Any] = field(default_factory=dict)
    # Lot 4: outcome of a reviewer's pagination request (describe_revision_outcome).
    revision: dict[str, Any] | None = None


def _forces_experience_pages(options: dict[str, Any]) -> bool:
    return bool(options.get("force_experiences_new_page") or options.get("force_page_break_before_experience_indexes"))


def _grouped_experience_options(options: dict[str, Any]) -> dict[str, Any]:
    grouped = deepcopy(options)
    grouped.update({
        "force_experiences_new_page": False,
        "force_page_break_before_experience_indexes": [],
        "allow_grouping": True,
    })
    return grouped


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
    pagination_goal: str | None = None,
    previous_report: dict[str, Any] | None = None,
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

    def _try_variant(name: str, opts: dict[str, Any], output_name: str, *, bounded: bool = True) -> LayoutVariantAttempt | None:
        if bounded and len(attempts) >= max_attempts:
            return None
        key = _stable_key(opts)
        if key in seen_options:
            return next((a for a in attempts if _stable_key(a.layout_options) == key), None)
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
        return attempts[-1]

    # Base render
    _try_variant("base", deepcopy(options), "output.pdf")

    # Deterministic retry on pure layout issues
    if attempts:
        first = attempts[0]
        if is_safe_layout_retry_report(first.qa_report) and len(attempts) < max_attempts:
            from .intelligence import build_layout_retry_options
            retry_options = build_layout_retry_options(options, first.qa_report)
            _try_variant("layout_retry", retry_options, "output_layout_retry.pdf")
        elif first.status == "passed" and _forces_experience_pages(options) and len(attempts) < max_attempts:
            # Heavy CVs put experiences on their own pages. That passes QA but
            # can cost pages; the grouped layout competes, the selector keeps
            # the shorter one at equal quality.
            _try_variant("grouped", _grouped_experience_options(options), "output_grouped.pdf")

    selection = select_best_layout_variant(attempts)
    if selection.selected is None and selection.hard_failure is None:
        raise RuntimeError("No layout variant produced a QA report")
    # A CV whose only failure is draftable (fidelity / taste, never contact
    # or assets) goes on as a draft: its layout is repaired the same way.
    draft_mode = selection.selected is None and _can_return_layout_hard_failure_as_draft(
        dict(selection.hard_failure.qa_report or {}) if selection.hard_failure else {}
    )
    if selection.selected is None and not draft_mode:
        raise RuntimeError(f"Layout hard failure: {selection.hard_failure.qa_report if selection.hard_failure else None}")

    def _usable(attempt: LayoutVariantAttempt | None) -> bool:
        if attempt is None:
            return False
        if not attempt.is_hard_failed:
            return True
        # Failed only on draftable grounds (a fidelity alert alone is
        # "failed" in classify_qa_report): delivered as a draft, like the base.
        return _can_return_layout_hard_failure_as_draft(dict(attempt.qa_report or {}))

    chosen: LayoutVariantAttempt = selection.selected or selection.hard_failure  # type: ignore[assignment]
    repair: dict[str, Any] = {}
    revision: dict[str, Any] | None = None

    # Lot 4 — deterministic retry of blocking layout defects (src/qa_defects.py):
    # renderer-only variants, the one with the fewest blocking defects wins.
    initial_blocking = sorted({str(d.get("code")) for d in blocking_defects(chosen.qa_report.get("defects"))})
    if layout_blocking_codes(chosen.qa_report):
        repair = {"initial_blocking": initial_blocking, "tried": []}
        for index, (name, opts) in enumerate(repair_variant_options(chosen.layout_options, chosen.qa_report)):
            attempt = _try_variant(name, opts, f"output_repair_{index}.pdf", bounded=False)
            if attempt is None:
                continue
            repair["tried"].append(name)
            if _usable(attempt) and pagination_cost(attempt.qa_report) < pagination_cost(chosen.qa_report):
                chosen = attempt
            if not layout_blocking_codes(chosen.qa_report):
                break
        repair["repaired"] = not blocking_defects(chosen.qa_report.get("defects"))
    elif initial_blocking:
        repair = {"initial_blocking": initial_blocking, "tried": [], "repaired": False}

    if pagination_goal:
        # Lot 4 — a reviewer's pagination request ("moins de pages",
        # "rééquilibre", "trop de vide", "sauts de page"): compact variants
        # compete, the fewest blocking defects / pages / blank wins, and the
        # outcome is described against the previous version.
        candidates = [chosen]
        for index, (name, opts) in enumerate(pagination_candidates(chosen.layout_options)):
            attempt = _try_variant(name, opts, f"output_revision_{index}.pdf", bounded=False)
            if _usable(attempt) and attempt not in candidates:
                candidates.append(attempt)  # type: ignore[arg-type]
        chosen = min(candidates, key=lambda a: (pagination_cost(a.qa_report), candidates.index(a)))
        revision = describe_revision_outcome(
            goal=pagination_goal,
            previous_report=previous_report or attempts[0].qa_report,
            chosen_report=chosen.qa_report,
            best_pages_tried=min(report_pages(a.qa_report) for a in candidates),
        )
        revision["variant"] = chosen.name
    elif should_try_page_saving(chosen.qa_report, chosen.layout_options):
        # Lot 4 — page saving: the last page is little filled, a compact
        # spacing may drop it. Kept only when it removes a page without
        # adding a blocking defect.
        attempt = _try_variant(
            "page_saving_compact", {**deepcopy(chosen.layout_options), **COMPACT}, "output_compact.pdf", bounded=False,
        )
        if (
            _usable(attempt)
            and not blocking_defects(attempt.qa_report.get("defects"))  # type: ignore[union-attr]
            and report_pages(attempt.qa_report) < report_pages(chosen.qa_report)  # type: ignore[union-attr]
        ):
            chosen = attempt  # type: ignore[assignment]
            repair = {**repair, "page_saved": True}

    report = dict(chosen.qa_report or {})
    if chosen.is_hard_failed:
        report["_draft_ready_for_layout_hard_failure"] = True
    return LayoutResult(
        pdf=chosen.pdf,
        qa_report=report,
        layout_options=chosen.layout_options,
        attempts_count=len(attempts),
        selected_variant=chosen.name,
        repair=repair,
        revision=revision,
    )


def _can_return_layout_hard_failure_as_draft(report: dict[str, Any]) -> bool:
    """Allow Telegram-like draft delivery for pure layout/taste failures only."""
    if not isinstance(report, dict):
        return False
    hard_safety_failed = (
        bool(report.get("contact_hits"))
        or not report.get("has_logo")
        or not report.get("has_watermark")
        or int(report.get("pages") or 0) <= 0
    )
    if hard_safety_failed:
        return False
    return bool(report.get("layout_issues") or report.get("human_taste"))
