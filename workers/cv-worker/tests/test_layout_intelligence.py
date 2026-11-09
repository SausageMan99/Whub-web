from src.layout_intelligence import build_layout_retry_options


def _report(*codes: str) -> dict:
    return {"layout_issues": [{"code": code} for code in codes]}


def test_sparse_retry_clears_forced_experience_breaks_and_uses_moderate_density():
    base_options = {
        "anti_crowding": False,
        "force_experiences_new_page": True,
        "force_page_break_before_experience_indexes": [1, 3],
        "page_dense_char_threshold": 2600,
        "max_used_ratio": 0.80,
        "readability_reserve": 170,
    }

    options = build_layout_retry_options(base_options, _report("page_too_sparse"))

    assert options["anti_crowding"] is True
    assert options["force_experiences_new_page"] is False
    assert options["force_page_break_before_experience_indexes"] == []
    assert options["allow_grouping"] is True
    assert options["page_dense_char_threshold"] >= 2850
    assert options["max_used_ratio"] >= 0.86
    assert base_options["force_experiences_new_page"] is True
    assert base_options["force_page_break_before_experience_indexes"] == [1, 3]


def test_dense_retry_keeps_break_hints_without_forcing_experience_pages():
    # The renderer breaks pages on the measured height (lot 1, 2026-11):
    # forcing each experience onto its own page only added half-empty pages,
    # so a dense / orphan retry now asks for more lines under each heading.
    base_options = {
        "anti_crowding": False,
        "force_experiences_new_page": False,
        "force_page_break_before_experience_indexes": [2],
        "page_dense_char_threshold": 2850,
        "max_used_ratio": 0.86,
    }

    options = build_layout_retry_options(base_options, _report("page_too_dense", "bad_page_break"))

    assert options["force_experiences_new_page"] is False
    assert options["force_page_break_before_experience_indexes"] == [2]
    assert options["min_lines_under_heading"] >= 3
    assert base_options["force_page_break_before_experience_indexes"] == [2]


def test_mixed_sparse_and_dense_retry_prefers_sparse_grouping():
    options = build_layout_retry_options(
        {
            "anti_crowding": False,
            "force_experiences_new_page": True,
            "force_page_break_before_experience_indexes": [1, 2, 3],
            "page_dense_char_threshold": 2500,
            "max_used_ratio": 0.75,
        },
        _report("last_page_sparse", "page_too_dense", "experience_orphan_heading"),
    )

    assert options["anti_crowding"] is True
    assert options["force_experiences_new_page"] is False
    assert options["force_page_break_before_experience_indexes"] == []
    assert options["page_dense_char_threshold"] >= 2850
    assert options["max_used_ratio"] >= 0.86
