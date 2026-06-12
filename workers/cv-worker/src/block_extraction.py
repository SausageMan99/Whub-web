from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import re

import fitz

from .content_blocks import ContentBlock

_FOOTER_RE = re.compile(r"^(page\s*)?\d+\s*(/|sur)\s*\d+$", re.IGNORECASE)


@dataclass(frozen=True)
class VisualTextBlock:
    page: int
    bbox: tuple[float, float, float, float]
    text: str


def is_probable_footer(text: str) -> bool:
    normalized = " ".join(text.strip().split())
    return bool(_FOOTER_RE.match(normalized))


def sort_visual_blocks(blocks: list[VisualTextBlock]) -> list[VisualTextBlock]:
    return sorted(blocks, key=lambda b: (b.page, round(b.bbox[1], 1), round(b.bbox[0], 1)))


def extract_visual_text_blocks(pdf_path: Path) -> list[VisualTextBlock]:
    doc = fitz.open(pdf_path)
    blocks: list[VisualTextBlock] = []
    for page_index, page in enumerate(doc):
        for raw in page.get_text("blocks"):
            if len(raw) < 5:
                continue
            x0, y0, x1, y1, text = raw[:5]
            cleaned = str(text).strip()
            if not cleaned:
                continue
            blocks.append(VisualTextBlock(page=page_index, bbox=(x0, y0, x1, y1), text=cleaned))
    return sort_visual_blocks(blocks)


def blocks_to_content_blocks(blocks: list[VisualTextBlock]) -> list[ContentBlock]:
    content: list[ContentBlock] = []
    for index, block in enumerate(sort_visual_blocks(blocks), start=1):
        footer = is_probable_footer(block.text)
        content.append(
            ContentBlock.from_text(
                "other",
                source_order=index,
                page=block.page,
                text=block.text,
                required=not footer,
                bbox=block.bbox,
            )
        )
    return content
