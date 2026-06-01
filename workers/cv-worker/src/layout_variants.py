from __future__ import annotations

from copy import deepcopy
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from .layout_intelligence import build_layout_retry_options
from .layout_retry import is_safe_layout_retry_report
from .qa import QAError, classify_qa_report

MAX_LAYOUT_VARIANT_ATTEMPTS = 2


@dataclass(frozen=True)
class LayoutVariantAttempt:
    name: str
    pdf: Path
    qa_report: dict[str, Any]
    status: str
    layout_options: dict[str, Any]

    @property
    def is_hard_failed(self) -> bool:
        return self.status == "failed"

    @property
    def score(self) -> int:
        human_taste = self.qa_report.get("human_taste") if isinstance(self.qa_report, dict) else None
        if isinstance(human_taste, dict) and isinstance(human_taste.get("score"), (int, float)):
            return int(human_taste["score"])
        if self.status == "passed":
            return 100
        if self.status == "draft":
            return 60
        return -1


@dataclass(frozen=True)
class LayoutVariantSelection:
    selected: LayoutVariantAttempt | None
    attempts: list[LayoutVariantAttempt]
    hard_failure: LayoutVariantAttempt | None = None

    @property
    def selected_pdf(self) -> Path | None:
        return self.selected.pdf if self.selected else None

    @property
    def selected_report(self) -> dict[str, Any] | None:
        return self.selected.qa_report if self.selected else None


def _stable_variant_key(options: dict[str, Any]) -> tuple[tuple[str, str], ...]:
    return tuple(sorted((str(key), repr(value)) for key, value in options.items()))


def select_best_layout_variant(attempts: list[LayoutVariantAttempt]) -> LayoutVariantSelection:
    """Pick the best non-hard-failed PDF by deterministic human-taste score.

    Hard blockers are never downgraded to draft warnings: a failed attempt is not
    selectable. If every attempt is hard-failed, return the first hard failure so
    the caller can fail the job with its original QA report.
    """
    safe_attempts = [attempt for attempt in attempts if not attempt.is_hard_failed]
    if not safe_attempts:
        hard_failure = attempts[0] if attempts else None
        return LayoutVariantSelection(selected=None, attempts=attempts, hard_failure=hard_failure)
    selected = max(
        safe_attempts,
        key=lambda attempt: (
            attempt.score,
            1 if attempt.status == "passed" else 0,
            -attempts.index(attempt),
        ),
    )
    return LayoutVariantSelection(selected=selected, attempts=attempts)


def evaluate_layout_variant(
    *,
    name: str,
    structured: dict[str, Any],
    workdir: Path,
    layout_options: dict[str, Any],
    render_pdf: Callable[..., Path],
    run_qa: Callable[..., dict[str, Any]],
    forbidden_names: list[str] | None = None,
    source_text: str | None = None,
    output_name: str,
) -> LayoutVariantAttempt:
    pdf = render_pdf(structured, workdir, layout_options=layout_options, output_name=output_name)
    try:
        qa_report = run_qa(pdf, forbidden_names=forbidden_names or [], source_text=source_text, structured_data=structured)
    except QAError as error:
        qa_report = error.report
    status, _warnings = classify_qa_report(qa_report)
    return LayoutVariantAttempt(
        name=name,
        pdf=pdf,
        qa_report=qa_report,
        status=status,
        layout_options=deepcopy(layout_options),
    )


def run_bounded_layout_variant_loop(
    *,
    structured: dict[str, Any],
    workdir: Path,
    base_options: dict[str, Any],
    render_pdf: Callable[..., Path],
    run_qa: Callable[..., dict[str, Any]],
    forbidden_names: list[str] | None = None,
    source_text: str | None = None,
    max_attempts: int = MAX_LAYOUT_VARIANT_ATTEMPTS,
) -> LayoutVariantSelection:
    """Render/QA a bounded set of layout variants and select the best safe PDF.

    The loop is deliberately conservative: base render first, then at most one
    deterministic retry when QA reports a pure soft-layout issue. No content is
    mutated; retry options are renderer-only layout hints.
    """
    attempts: list[LayoutVariantAttempt] = []
    seen_options: set[tuple[tuple[str, str], ...]] = set()

    def _try_variant(name: str, options: dict[str, Any], output_name: str) -> None:
        if len(attempts) >= max_attempts:
            return
        key = _stable_variant_key(options)
        if key in seen_options:
            return
        seen_options.add(key)
        attempts.append(
            evaluate_layout_variant(
                name=name,
                structured=structured,
                workdir=workdir,
                layout_options=options,
                render_pdf=render_pdf,
                run_qa=run_qa,
                forbidden_names=forbidden_names,
                source_text=source_text,
                output_name=output_name,
            )
        )

    _try_variant("base", deepcopy(base_options), "output.pdf")
    if attempts:
        first = attempts[0]
        if is_safe_layout_retry_report(first.qa_report) and len(attempts) < max_attempts:
            retry_options = build_layout_retry_options(base_options, first.qa_report)
            _try_variant("layout_retry", retry_options, "output_layout_retry.pdf")

    return select_best_layout_variant(attempts)
