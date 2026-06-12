from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import math
from typing import Literal

BlockType = Literal[
    "profile",
    "skills",
    "experience",
    "education",
    "languages",
    "certifications",
    "other",
]

_REQUIRED_TYPES = {"profile", "skills", "experience", "education", "languages", "certifications"}


def estimate_lines(text: str, chars_per_line: int = 72) -> int:
    lines = 0
    for raw_line in text.splitlines() or [text]:
        stripped = raw_line.strip()
        if not stripped:
            lines += 1
            continue
        lines += max(1, math.ceil(len(stripped) / chars_per_line))
    return lines


def stable_block_id(block_type: str, source_order: int, text: str) -> str:
    digest = hashlib.sha1(text.strip().encode("utf-8")).hexdigest()[:8]
    safe_type = "".join(ch if ch.isalnum() else "_" for ch in block_type.lower()).strip("_") or "block"
    return f"{safe_type}_{source_order:03d}_{digest}"


@dataclass(frozen=True)
class ContentBlock:
    id: str
    type: BlockType
    source_order: int
    page: int
    text: str
    char_count: int
    estimated_lines: int
    confidence: float = 1.0
    required: bool = True
    bbox: tuple[float, float, float, float] | None = None
    metadata: dict[str, str | int | float | bool] = field(default_factory=dict)

    @classmethod
    def from_text(
        cls,
        block_type: BlockType,
        source_order: int,
        page: int,
        text: str,
        *,
        confidence: float = 1.0,
        required: bool | None = None,
        bbox: tuple[float, float, float, float] | None = None,
    ) -> "ContentBlock":
        effective_required = block_type in _REQUIRED_TYPES if required is None else required
        return cls(
            id=stable_block_id(block_type, source_order, text),
            type=block_type,
            source_order=source_order,
            page=page,
            text=text,
            char_count=len(text),
            estimated_lines=estimate_lines(text),
            confidence=confidence,
            required=effective_required,
            bbox=bbox,
        )


@dataclass(frozen=True)
class SourceDocument:
    blocks: list[ContentBlock]
    source_profile: str | None = None
    raw_chars: int = 0
    sanitized_chars: int = 0

    def ordered_blocks(self) -> list[ContentBlock]:
        return sorted(self.blocks, key=lambda b: (b.source_order, b.page, b.id))

    def required_blocks(self) -> list[ContentBlock]:
        return [block for block in self.ordered_blocks() if block.required]
