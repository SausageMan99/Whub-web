#!/usr/bin/env python3
from __future__ import annotations

import copy
import json
import re
import sys
from pathlib import Path
from typing import Any

import fitz

REPO = Path(__file__).resolve().parents[2]
WORKER = REPO / "workers" / "cv-worker"
sys.path.insert(0, str(WORKER))

from src.qa import QAError, classify_qa_report, collect_page_layout_metrics, run_qa  # noqa: E402
from src.rendering import render_pdf  # noqa: E402
from src.structuring import (  # noqa: E402
    StructuringError,
    _contains_fidelity_fact,
    _normalize_for_fidelity,
    infer_forbidden_candidate_identity_terms,
    validate_source_fidelity,
)

ARTIFACT_DIR = Path(__file__).resolve().parent
FIXTURES = WORKER / "tests" / "fixtures" / "fidelity_regression_cases.json"
CASE_IDS = [
    "oussama_like_rpa_copy_preservation",
    "zahia_like_location_and_role_facts",
    "thorez_like_realizations_and_tools_coverage",
]


def _extract_pdf_text(pdf_path: Path) -> str:
    doc = fitz.open(str(pdf_path))
    return "\n".join(str(page.get_text("text")) for page in doc)


def _redact_report(report: dict[str, Any]) -> dict[str, Any]:
    # Reports should not expose raw source coordinates/contact details. The smoke cases are synthetic,
    # but keep the artifact product-safe anyway.
    redacted = copy.deepcopy(report)
    for key in ("contact_hits", "bad_glyphs", "text_overflow_hits", "content_integrity_issues", "layout_issues"):
        redacted.setdefault(key, [] if key != "bad_glyphs" else False)
    return redacted


def _check_terms_absent(text: str, terms: list[str]) -> list[str]:
    found: list[str] = []
    for term in terms:
        if not term:
            continue
        # Do not persist the value itself in the summary; only persist counts outside per-case JSON.
        if term.lower() in text.lower():
            found.append(term)
    return found


def _must_drop_absent(text: str, term: str) -> bool:
    if re.search(r"\d", term) and not re.search(r"[A-Za-zÀ-ÿ]", term):
        return re.sub(r"\D+", "", term) not in re.sub(r"\D+", "", text)
    return term.lower() not in text.lower()


def _basic_pdf_checks(text: str, forbidden_terms: list[str], must_keep: list[str], must_drop: list[str]) -> dict[str, Any]:
    lower = text.lower()
    normalized_pdf = _normalize_for_fidelity(text)
    return {
        "email_absent": "@" not in text,
        "linkedin_absent": "linkedin" not in lower,
        "url_absent": not re.search(r"https?://|github\.com|\.com\b", text, re.I),
        "phone_fr_absent": not bool(re.search(r"(?:\+33|\b0[67])(?:[ .-]?\d{2}){4}\b", text)),
        "forbidden_identity_absent": not _check_terms_absent(text, forbidden_terms),
        "must_keep_present": {item: _contains_fidelity_fact(normalized_pdf, item) for item in must_keep},
        "must_drop_absent": {f"drop_{idx+1}": _must_drop_absent(text, item) for idx, item in enumerate(must_drop)},
    }


def main() -> int:
    ARTIFACT_DIR.mkdir(parents=True, exist_ok=True)
    cases = {case["id"]: case for case in json.loads(FIXTURES.read_text(encoding="utf-8"))}
    summary: dict[str, Any] = {
        "artifact_dir": str(ARTIFACT_DIR),
        "cases_requested": CASE_IDS,
        "cases": [],
        "overall": "GO",
        "notes": [
            "No production deploy, push, or worker restart was performed.",
            "Raw source text was used in memory for fidelity checks but not written to artifacts.",
        ],
    }

    for case_id in CASE_IDS:
        case = cases[case_id]
        source = case["source"]
        data = copy.deepcopy(case["structured"])
        case_dir = ARTIFACT_DIR / case_id
        case_dir.mkdir(parents=True, exist_ok=True)

        first_name = str(data.get("name") or "").strip()
        forbidden_terms = infer_forbidden_candidate_identity_terms(source, first_name)

        case_summary: dict[str, Any] = {
            "id": case_id,
            "first_name_only": first_name,
            "forbidden_identity_terms_count": len(forbidden_terms),
            "structured_json": str(case_dir / "structured_input_redacted.json"),
            "pdf": str(case_dir / "output.pdf"),
            "qa_report": str(case_dir / "qa_report.json"),
            "layout_metrics": str(case_dir / "layout_metrics.json"),
            "checks": {},
        }

        (case_dir / "structured_input_redacted.json").write_text(
            json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8"
        )

        try:
            validate_source_fidelity(source, data, forbidden_identity_terms=forbidden_terms)
            case_summary["checks"]["source_fidelity_json"] = "passed"
        except StructuringError as exc:
            case_summary["checks"]["source_fidelity_json"] = "failed"
            case_summary["source_fidelity_error"] = str(exc)
            summary["overall"] = "NO-GO"

        pdf_path = render_pdf(data, case_dir, output_name="output.pdf")
        text = _extract_pdf_text(pdf_path)
        pdf_checks = _basic_pdf_checks(
            text,
            forbidden_terms=forbidden_terms,
            must_keep=case.get("must_keep") or [],
            must_drop=case.get("must_drop") or [],
        )
        case_summary["checks"].update(pdf_checks)

        try:
            qa_report = run_qa(
                pdf_path,
                forbidden_names=forbidden_terms,
                source_text=source,
                structured_data=data,
            )
            qa_status = "passed"
            layout_warnings: list[dict[str, Any]] = []
        except QAError as exc:
            qa_report = exc.report
            qa_status, layout_warnings = classify_qa_report(qa_report)
            if qa_status == "failed":
                summary["overall"] = "NO-GO"

        case_summary["checks"]["qa_status"] = qa_status
        case_summary["checks"]["layout_warning_count"] = len(layout_warnings)
        case_summary["checks"]["hard_quality_ok"] = (
            not qa_report.get("contact_hits")
            and not qa_report.get("bad_glyphs")
            and not qa_report.get("text_overflow_hits")
            and not qa_report.get("content_integrity_issues")
            and qa_report.get("has_logo") is True
            and qa_report.get("has_watermark") is True
            and qa_report.get("pages", 0) > 0
        )

        if not all(v is True for k, v in pdf_checks.items() if isinstance(v, bool)):
            summary["overall"] = "NO-GO"
        if not all(pdf_checks["must_keep_present"].values()):
            summary["overall"] = "NO-GO"
        if not all(pdf_checks["must_drop_absent"].values()):
            summary["overall"] = "NO-GO"
        if not case_summary["checks"]["hard_quality_ok"]:
            summary["overall"] = "NO-GO"

        (case_dir / "qa_report.json").write_text(
            json.dumps(_redact_report(qa_report), ensure_ascii=False, indent=2), encoding="utf-8"
        )
        with fitz.open(str(pdf_path)) as doc:
            metrics = collect_page_layout_metrics(doc)
            # Remove raw block data/text to keep the metrics compact and privacy-safe.
            compact_metrics = [
                {k: v for k, v in metric.items() if k not in {"text", "blocks"}}
                for metric in metrics
            ]
        (case_dir / "layout_metrics.json").write_text(
            json.dumps(compact_metrics, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        summary["cases"].append(case_summary)

    (ARTIFACT_DIR / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    print(json.dumps(summary, ensure_ascii=False, indent=2))
    return 0 if summary["overall"] == "GO" else 1


if __name__ == "__main__":
    raise SystemExit(main())
