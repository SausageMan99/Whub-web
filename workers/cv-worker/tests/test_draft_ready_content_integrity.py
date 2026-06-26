from src.qa import classify_qa_report


def _report(**overrides):
    report = {
        "passed": False,
        "pages": 2,
        "contact_hits": [],
        "bad_glyphs": False,
        "content_integrity_issues": [],
        "text_overflow_hits": [],
        "layout_issues": [],
        "has_logo": True,
        "has_watermark": True,
    }
    report.update(overrides)
    return report


def test_classify_qa_report_content_integrity_without_marker_returns_failed():
    """Content integrity issues alone must return 'failed', not 'draft' or 'passed'."""
    report = _report(
        content_integrity_issues=[
            {"code": "pdf_fact_absent_from_source", "fact": "X"}
        ],
    )

    status, warnings = classify_qa_report(report)

    assert status == "failed"
    assert warnings == []


def test_classify_qa_report_content_integrity_with_marker_returns_draft():
    """Content integrity issues with the explicit layout_hard_failure marker return 'draft'."""
    report = _report(
        content_integrity_issues=[
            {"code": "pdf_fact_absent_from_source", "fact": "X"}
        ],
        _draft_ready_for_layout_hard_failure=True,
    )

    status, warnings = classify_qa_report(report)

    assert status == "draft"
    assert warnings == report["content_integrity_issues"]


def test_classify_qa_report_only_layout_issues_returns_draft():
    """Layout-only issues (known soft code) still return 'draft'."""
    report = _report(
        layout_issues=[{"code": "page_too_sparse", "page": 2}],
    )

    status, warnings = classify_qa_report(report)

    assert status == "draft"
    assert warnings == report["layout_issues"]
