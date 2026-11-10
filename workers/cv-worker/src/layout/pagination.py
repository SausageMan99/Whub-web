"""Variantes de mise en page déterministes (lot 4, 2026-11).

Trois usages, tous sans appel LLM et sans toucher au contenu (seules des
options du renderer changent) :

1. réparer un défaut BLOQUANT d'origine mise en page (src/qa_defects.py) :
   titre orphelin, page intermédiaire quasi vide, texte hors page, contenu
   absent du PDF -> ``repair_variant_options`` ;
2. gagner une page quand la dernière est peu remplie -> ``compact`` essayé et
   retenu seulement s'il retire une page sans défaut bloquant ;
3. répondre à une demande de pagination du relecteur (« moins de pages »,
   « rééquilibre », « trop de vide », « sauts de page ») ->
   ``pagination_candidates`` puis ``describe_revision_outcome``, qui dit au
   relecteur ce qui a changé, ou pourquoi rien ne peut changer.

Les variantes se comparent par ``pagination_cost`` : défauts bloquants
d'abord, puis nombre de pages, puis blanc laissé sur les pages.
"""
from __future__ import annotations

from copy import deepcopy
from typing import Any

from ..qa_defects import LAYOUT, blocking_defects

COMPACT = {"spacing": "compact"}
KEEP_WITH_NEXT = {"min_lines_under_heading": 3, "min_experience_opener_lines": 4}
SHORT_OPENER = {"min_experience_opener_lines": 2}

# The last page under this fill: a compact rendering may save a page.
PAGE_SAVING_LAST_FILL = 0.50
# A revision must gain a page, or this much blank (sum of page fills).
REVISION_MIN_BLANK_GAIN = 0.10
MAX_REPAIR_VARIANTS = 3


def page_fills(report: dict[str, Any] | None) -> list[float]:
    """Fill of each page (qa.collect_pagination_metrics), or, for an older
    report without it, the used ratio of its layout metrics."""
    report = report if isinstance(report, dict) else {}
    pagination = report.get("pagination") if isinstance(report.get("pagination"), dict) else {}
    fills = pagination.get("page_fill")
    if isinstance(fills, list) and fills:
        return [float(f) for f in fills]
    metrics = report.get("layout_metrics") or (report.get("human_taste") or {}).get("page_metrics") or []
    return [float(m.get("used_ratio") or 0.0) for m in metrics if isinstance(m, dict)]


def blank_amount(fills: list[float]) -> float:
    """Blank left on the pages: every page but the last counts its empty
    part; the last counts only what is missing to 35 %."""
    if not fills:
        return 0.0
    blank = sum(max(0.0, 1.0 - fill) for fill in fills[:-1])
    if len(fills) > 1:
        blank += max(0.0, 0.35 - fills[-1])
    return round(blank, 3)


def report_pages(report: dict[str, Any] | None) -> int:
    return int((report or {}).get("pages") or len(page_fills(report)) or 0)


def pagination_cost(report: dict[str, Any] | None) -> tuple[int, int, float]:
    return (
        len(blocking_defects((report or {}).get("defects"))),
        report_pages(report),
        blank_amount(page_fills(report)),
    )


def layout_blocking_codes(report: dict[str, Any] | None) -> set[str]:
    return {
        str(d.get("code")) for d in blocking_defects((report or {}).get("defects"))
        if d.get("origin") == LAYOUT
    }


def repair_variant_options(base_options: dict[str, Any], report: dict[str, Any] | None) -> list[tuple[str, dict[str, Any]]]:
    """Renderer-only variants for the blocking layout defects of `report`."""
    codes = layout_blocking_codes(report)
    if not codes:
        return []
    variants: list[tuple[str, dict[str, Any]]] = []
    break_issue = bool(codes & {"heading_orphaned_at_page_bottom", "page_nearly_empty"})
    if break_issue:
        variants.append(("repair_keep_with_next", {**deepcopy(base_options), **KEEP_WITH_NEXT}))
    variants.append(("repair_compact", {**deepcopy(base_options), **COMPACT}))
    if break_issue:
        variants.append(("repair_compact_keep_with_next", {**deepcopy(base_options), **COMPACT, **KEEP_WITH_NEXT}))
    else:
        variants.append(("repair_grouped", {
            **deepcopy(base_options), "force_experiences_new_page": False,
            "force_page_break_before_experience_indexes": [], "allow_grouping": True,
        }))
    return variants[:MAX_REPAIR_VARIANTS]


def should_try_page_saving(report: dict[str, Any] | None, options: dict[str, Any]) -> bool:
    fills = page_fills(report)
    return (
        len(fills) >= 2
        and fills[-1] < PAGE_SAVING_LAST_FILL
        and options.get("spacing") != "compact"
        and not blocking_defects((report or {}).get("defects"))
    )


def pagination_candidates(base_options: dict[str, Any]) -> list[tuple[str, dict[str, Any]]]:
    """Variants tried for a pagination request of the reviewer."""
    return [
        ("revision_compact", {**deepcopy(base_options), **COMPACT}),
        ("revision_compact_short_opener", {**deepcopy(base_options), **COMPACT, **SHORT_OPENER}),
        ("revision_short_opener", {**deepcopy(base_options), **SHORT_OPENER}),
    ]


def _percent_list(fills: list[float]) -> str:
    return " / ".join(f"{round(fill * 100)} %" for fill in fills)


def describe_revision_outcome(
    *,
    goal: str,
    previous_report: dict[str, Any] | None,
    chosen_report: dict[str, Any] | None,
    best_pages_tried: int | None = None,
) -> dict[str, Any]:
    """What a pagination revision changed, in French, for the version note.

    ``improved`` is False when the new version has as many pages and about
    as much blank as the previous one: the note then says why (the content
    really fills the pages) instead of pretending the request was applied."""
    previous_fills = page_fills(previous_report)
    new_fills = page_fills(chosen_report)
    previous_pages = report_pages(previous_report) or len(previous_fills)
    new_pages = report_pages(chosen_report) or len(new_fills)
    previous_blank = blank_amount(previous_fills)
    new_blank = blank_amount(new_fills)
    fewer_pages = bool(previous_pages) and new_pages < previous_pages
    less_blank = bool(previous_fills) and new_pages <= previous_pages and previous_blank - new_blank >= REVISION_MIN_BLANK_GAIN
    improved = fewer_pages or less_blank
    fills_text = _percent_list(new_fills)
    if fewer_pages:
        message = (
            f"Mise en page resserrée : {previous_pages} pages -> {new_pages} "
            f"(pages remplies à {fills_text}), sans retirer de contenu."
        )
    elif less_blank:
        message = (
            f"Pages rééquilibrées : {new_pages} pages, moins de blanc "
            f"(pages remplies à {fills_text} contre {_percent_list(previous_fills)})."
        )
    else:
        tried = best_pages_tried if best_pages_tried is not None else new_pages
        if goal == "fewer_pages":
            message = (
                f"Impossible de passer sous {new_pages} page{'s' if new_pages > 1 else ''} sans retirer de contenu : "
                f"le texte remplit réellement les pages ({fills_text}), même avec un interligne resserré "
                f"({tried} page{'s' if tried > 1 else ''}). Indique ce qui peut être raccourci ou retiré."
            )
        else:
            message = (
                f"Mise en page déjà équilibrée : {new_pages} page{'s' if new_pages > 1 else ''} remplies à {fills_text}, "
                "aucune page intermédiaire à moitié vide ; la dernière page porte la fin du contenu. "
                "Rien à déplacer sans retirer de contenu."
            )
    return {
        "goal": goal,
        "improved": improved,
        "previous_pages": previous_pages,
        "new_pages": new_pages,
        "previous_blank": previous_blank,
        "new_blank": new_blank,
        "new_fill": new_fills,
        "message": message,
    }


__all__ = [
    "COMPACT", "KEEP_WITH_NEXT", "SHORT_OPENER", "PAGE_SAVING_LAST_FILL", "REVISION_MIN_BLANK_GAIN",
    "page_fills", "blank_amount", "report_pages", "pagination_cost", "layout_blocking_codes",
    "repair_variant_options", "should_try_page_saving", "pagination_candidates",
    "describe_revision_outcome",
]
