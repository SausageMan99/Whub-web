from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import fitz

from .content_blocks import SourceDocument
from .content_preserving_rendering import render_content_preserving_pdf
from .responsive_layout_variants import build_layout_variants
from .source_coverage import compare_required_block_coverage


@dataclass(frozen=True)
class ContentPreservingResult:
    final_pdf_path: Path
    variant: str
    missing_required_blocks: list[dict[str, int | str]]


def _extract_pdf_text(path: Path) -> str:
    return "\n".join(page.get_text("text") for page in fitz.open(path))


def render_best_content_preserving_variant(
    document: SourceDocument,
    *,
    candidate_first_name: str,
    output_dir: Path,
) -> ContentPreservingResult:
    output_dir.mkdir(parents=True, exist_ok=True)
    best: ContentPreservingResult | None = None
    for plan in build_layout_variants(document):
        out = output_dir / f"{plan.strategy}.pdf"
        render_content_preserving_pdf(
            document,
            candidate_first_name=candidate_first_name,
            layout_plan=plan,
            output_path=out,
        )
        rendered_text = _extract_pdf_text(out)
        missing = compare_required_block_coverage(document, rendered_text)
        candidate = ContentPreservingResult(
            final_pdf_path=out,
            variant=plan.strategy,
            missing_required_blocks=missing,
        )
        if best is None or len(candidate.missing_required_blocks) < len(best.missing_required_blocks):
            best = candidate
    if best is None:
        raise RuntimeError("No content-preserving layout variant rendered")
    return best
