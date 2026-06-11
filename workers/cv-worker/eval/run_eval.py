"""W hub CV Factory offline evaluation runner.

The runner validates a generated CV result (PDF text + QA report) against
the assertions declared in a benchmark case. It is intentionally pure and
side-effect free: it never calls the model, never reads from Supabase.

Usage:

    uv run python eval/run_eval.py --case cases/example_case.json --result /tmp/result.json

The result file is expected to be a JSON object with at least::

    {
        "status": "ready|draft_ready|needs_human_review|qa_failed|failed",
        "pdf_text": "the full extracted PDF text",
        "qa_report": {
            "pages": 3,
            "layout_issues": [{"code": "last_page_sparse", "page": 3, ...}]
        }
    }
"""
from __future__ import annotations

import argparse
import json
import re
from pathlib import Path
from typing import Any


def _layout_codes(qa_report: dict[str, Any]) -> set[str]:
    return {
        str(issue.get("code"))
        for issue in qa_report.get("layout_issues", [])
        if isinstance(issue, dict) and issue.get("code")
    }


def evaluate_case_result(case: dict[str, Any], result: dict[str, Any]) -> dict[str, Any]:
    """Return a verdict describing whether the result satisfies the case."""
    assertions = case.get("assertions", {}) or {}
    pdf_text = str(result.get("pdf_text") or "")
    qa_report = result.get("qa_report") if isinstance(result.get("qa_report"), dict) else {}
    failures: list[str] = []

    expected_status = assertions.get("expected_status")
    if expected_status and result.get("status") != expected_status:
        failures.append(f"status:{result.get('status')}!=expected:{expected_status}")

    for term in assertions.get("required_terms", []) or []:
        if str(term) not in pdf_text:
            failures.append(f"missing_term:{term}")

    for pattern in assertions.get("forbidden_patterns", []) or []:
        if re.search(str(pattern), pdf_text, re.I):
            failures.append(f"forbidden_pattern:{pattern}")

    max_pages = assertions.get("max_pages")
    if isinstance(max_pages, int):
        pages = int(qa_report.get("pages") or 0)
        if pages > max_pages:
            failures.append(f"pages:{pages}>max:{max_pages}")

    disallowed_codes = set(assertions.get("disallowed_qa_codes", []) or [])
    hit_codes = _layout_codes(qa_report) & disallowed_codes
    for code in sorted(hit_codes):
        failures.append(f"disallowed_qa_code:{code}")

    return {
        "case_id": case.get("id"),
        "passed": not failures,
        "failures": failures,
    }


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument("--case", required=True, type=Path)
    parser.add_argument("--result", required=True, type=Path)
    args = parser.parse_args()

    case = json.loads(args.case.read_text(encoding="utf-8"))
    result = json.loads(args.result.read_text(encoding="utf-8"))
    print(json.dumps(evaluate_case_result(case, result), indent=2, ensure_ascii=False))
    verdict = evaluate_case_result(case, result)
    raise SystemExit(0 if verdict["passed"] else 1)


if __name__ == "__main__":
    main()
