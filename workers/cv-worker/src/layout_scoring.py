from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class LayoutScore:
    variant: str
    missing_required_blocks: int
    contact_hits: int
    identity_hits: int
    sparse_pages: int
    dense_pages: int
    page_count: int

    def hard_failed(self) -> bool:
        return self.missing_required_blocks > 0 or self.contact_hits > 0 or self.identity_hits > 0

    def score(self) -> int:
        total = 100
        total -= self.missing_required_blocks * 1000
        total -= self.contact_hits * 1000
        total -= self.identity_hits * 1000
        total -= self.sparse_pages * 15
        total -= self.dense_pages * 25
        total -= max(0, self.page_count - 4) * 5
        return total


def choose_best_layout_score(scores: list[LayoutScore]) -> LayoutScore:
    if not scores:
        raise ValueError("No layout scores provided")
    return max(scores, key=lambda item: item.score())
