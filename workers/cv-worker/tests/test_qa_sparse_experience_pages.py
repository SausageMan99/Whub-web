import tempfile
from pathlib import Path

import fitz
import pytest

from src.qa import find_layout_issues


def _build_synthetic_pdf() -> tuple[Path, tempfile.TemporaryDirectory]:
    tmp = tempfile.TemporaryDirectory()
    path = Path(tmp.name) / "sparse_experience.pdf"
    doc = fitz.open()

    # Page 1: full header (high density ~0.58)
    page = doc.new_page(width=595, height=842)
    page.insert_text((50, 800), "Jean Dupont", fontsize=16)
    page.insert_text((50, 780), "Architecte Cloud", fontsize=11)
    page.insert_text((50, 760), "Expériences professionnelles", fontsize=11)
    page.insert_text((50, 740), "Compétences techniques", fontsize=11)
    y = 720
    for i in range(41):
        page.insert_text((50, y), f"Ligne {i+1}: Architecture cloud et DevOps.", fontsize=9)
        y -= 12

    # Page 2: experience-only page with used_ratio ~0.41 (V45 regression class)
    page = doc.new_page(width=595, height=842)
    page.insert_text((50, 800), "Expériences professionnelles", fontsize=11)
    y = 780
    for i in range(27):
        page.insert_text((50, y), f"Mission {i+1}: Développement et architecture pour client.", fontsize=9)
        y -= 12

    # Page 3: experience-only page with used_ratio ~0.63 (should NOT be flagged)
    page = doc.new_page(width=595, height=842)
    page.insert_text((50, 800), "Expériences professionnelles", fontsize=11)
    y = 780
    for i in range(44):
        page.insert_text(
            (50, y),
            f"Mission {i+1}: Développement et architecture pour client avec beaucoup de texte additionnel nécessaire.",
            fontsize=9,
        )
        y -= 12

    # Page 4: experience-only page with used_ratio ~0.45 (should be flagged)
    page = doc.new_page(width=595, height=842)
    page.insert_text((50, 800), "Expériences professionnelles", fontsize=11)
    y = 780
    for i in range(29):
        page.insert_text((50, y), f"Mission {i+1}: Développement et architecture pour client.", fontsize=9)
        y -= 12

    # Page 5: experience-only page with used_ratio ~0.41.
    # Sparse by existing last-page logic (few chars/blocks).
    page = doc.new_page(width=595, height=842)
    page.insert_text((50, 750), "Expériences professionnelles", fontsize=12)
    page.insert_text((50, 550), "2020 - 2022 Consultant.", fontsize=9)
    page.insert_text((50, 420), "Environnement technique: Python, AWS", fontsize=9)

    doc.save(path)
    doc.close()
    return path, tmp


def test_sparse_experience_pages_detected():
    path, tmp = _build_synthetic_pdf()
    try:
        doc = fitz.open(path)
        issues = find_layout_issues(doc)
        doc.close()

        codes_by_page = {}
        for issue in issues:
            codes_by_page.setdefault(issue["page"], []).append(issue["code"])

        # Page 1 should not be flagged as sparse
        assert "page_too_sparse" not in codes_by_page.get(1, [])

        # Page 2 should be flagged with page_too_sparse (new experience sparse detection)
        assert "page_too_sparse" in codes_by_page.get(2, []), (
            f"Page 2 (used_ratio ~0.41) should be flagged as page_too_sparse, got: {codes_by_page.get(2, [])}"
        )

        # Page 3 should NOT be flagged as sparse
        assert "page_too_sparse" not in codes_by_page.get(3, []), (
            f"Page 3 (used_ratio ~0.63) should not be sparse, got: {codes_by_page.get(3, [])}"
        )

        # Page 4 should be flagged with page_too_sparse (new experience sparse detection)
        assert "page_too_sparse" in codes_by_page.get(4, []), (
            f"Page 4 (used_ratio ~0.45) should be flagged as page_too_sparse, got: {codes_by_page.get(4, [])}"
        )

        # Page 5 should be flagged by existing last-page sparse logic
        assert "last_page_sparse" in codes_by_page.get(5, []), (
            f"Page 5 (last page, sparse) should be flagged as last_page_sparse, got: {codes_by_page.get(5, [])}"
        )
    finally:
        tmp.cleanup()
