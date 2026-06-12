from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re

from .content_blocks import ContentBlock, SourceDocument

_TOKEN_RE = re.compile(r"[a-z0-9à-ÿ]+", re.IGNORECASE)


@dataclass(frozen=True)
class CoverageEntry:
    block_id: str
    block_type: str
    source_order: int
    required: bool
    fingerprint: str
    token_count: int


@dataclass(frozen=True)
class CoverageLedger:
    entries: list[CoverageEntry]

    def required_entries(self) -> list[CoverageEntry]:
        return [entry for entry in self.entries if entry.required]


def _tokens(text: str) -> list[str]:
    return [match.group(0).lower() for match in _TOKEN_RE.finditer(text)]


def _fingerprint(text: str) -> str:
    normalized = " ".join(_tokens(text))
    return hashlib.sha1(normalized.encode("utf-8")).hexdigest()[:12]


def build_coverage_ledger(document: SourceDocument) -> CoverageLedger:
    entries = []
    for block in document.ordered_blocks():
        tokens = _tokens(block.text)
        entries.append(
            CoverageEntry(
                block_id=block.id,
                block_type=block.type,
                source_order=block.source_order,
                required=block.required,
                fingerprint=_fingerprint(block.text),
                token_count=len(tokens),
            )
        )
    return CoverageLedger(entries=entries)
