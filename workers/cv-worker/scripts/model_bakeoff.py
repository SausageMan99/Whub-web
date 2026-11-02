#!/usr/bin/env python3
"""Compare structuring models on the CV test bank, offline (no DB writes).

Each case runs the worker pipeline locally — extraction, sanitization,
schema-constrained structuring via OpenRouter with the model under test,
post-structuring passes, layout + QA — and records status, warnings, pages,
duration, cost and two source-fidelity measures computed against the
sanitized source:

- coverage: share of substantial source lines found verbatim in the output
- exact_copy: share of experience content strings that are verbatim source extracts

Usage (one process per model, since the model is a process-wide setting):
  python scripts/model_bakeoff.py run --model google/gemini-2.5-flash --out out/gemini25.jsonl
  python scripts/model_bakeoff.py report out/*.jsonl
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
import threading
import time
import unicodedata
from pathlib import Path
from statistics import mean

WORKER_ROOT = Path(__file__).resolve().parents[1]
REPO_ROOT = WORKER_ROOT.parents[1]
sys.path.insert(0, str(WORKER_ROOT))

CASES: dict[str, tuple[str, str]] = {
    "oussama": ("Oussama_RPA_copy_preservation", "Oussama"),
    "zahia": ("Zahia_location_and_role_facts", "Zahia"),
    "thorez": ("Thorez_realizations_and_tools_coverage", "Nicolas"),
    "dense": ("Dense_skills_pagination", "Oussama"),
    "sanitize": ("Sanitizer_contact_strip", "Jean"),
    "hodard": ("Hodard_continuity", "Florian"),
    "rayan": ("Rayan_prod_e2e", "Rayan"),
    "amina": ("AMINA_QA_Salesforce", "Amina"),
    "benjamin": ("Benjamin_control_chars", "Benjamin"),
    "noel": ("Noel_json_invalid", "François-Pierre"),
    "yannick": ("Yannick_long_cv_json", "Yannick"),
}


def _norm(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower()
    text = re.sub(r"[•●▪◦·\-–—*]+\s", " ", text)
    return re.sub(r"\s+", " ", text).strip()


def _strings(node) -> list[str]:
    if isinstance(node, str):
        return [node]
    if isinstance(node, dict):
        return [s for value in node.values() for s in _strings(value)]
    if isinstance(node, list):
        return [s for value in node for s in _strings(value)]
    return []


def fidelity_metrics(source_text: str, structured: dict) -> dict:
    source_norm = _norm(source_text)
    output_norm = _norm(" ".join(_strings(structured)))
    source_lines = [_norm(line) for line in source_text.splitlines()]
    substantial = [line for line in source_lines if len(line) >= 30]
    covered = sum(1 for line in substantial if line in output_norm)
    contents = [
        _norm(item)
        for exp in structured.get("experiences") or []
        for section in exp.get("sections") or []
        for item in (section.get("content") or [])
        if isinstance(item, str) and len(_norm(item)) >= 30
    ]
    exact = sum(1 for item in contents if item in source_norm)
    return {
        "coverage": round(covered / len(substantial), 3) if substantial else None,
        "exact_copy": round(exact / len(contents), 3) if contents else None,
        "experiences": len(structured.get("experiences") or []),
        "skill_items": sum(len(s.get("items") or []) for s in structured.get("skills") or []),
    }


def run_case(case: str, model: str, out_dir: Path) -> dict:
    from src import llm_backend
    from src import main as m
    from src.extraction import extract_pdf_text
    from src.source_sanitizer import sanitize_source_text
    from src.structuring import build_whub_json, classify_structuring_error

    folder, first_name = CASES[case]
    pdf = REPO_ROOT / "cv_test_bank" / folder / "input.pdf"
    workdir = out_dir / model.replace("/", "__") / case
    workdir.mkdir(parents=True, exist_ok=True)
    usage: list[dict] = []
    lock = threading.Lock()

    def observe(record: dict) -> None:
        with lock:
            usage.append(record)

    llm_backend.usage_observer = observe
    result: dict = {"case": case, "model": model}
    start = time.perf_counter()
    try:
        text = extract_pdf_text(pdf)
        sanitized = sanitize_source_text(text, first_name).text
        structured = build_whub_json(sanitized, "", [], first_name)
        structured = m._apply_source_wins_post_structuring(structured, pdf)
        m.enforce_client_first_name(structured, first_name)
        soft = structured.pop("_fidelity_soft_warnings", None) or []
        structured = m.sanitize_contact_in_json(structured)
        m.assert_no_contact_in_json(structured)
        result.update(fidelity_metrics(sanitized, structured))
        layout = m.run_layout(
            structured=structured,
            workdir=workdir,
            render_pdf=m.render_pdf,
            run_qa=m.run_qa,
            forbidden_names=m.forbidden_candidate_name_parts(first_name, text),
            source_text=sanitized,
            base_options=m.build_layout_packing_options(structured),
        )
        status, layout_warnings = m.classify_qa_report(layout.qa_report)
        if soft and status == "passed":
            status = "draft"
        result.update(
            status=status,
            pages=layout.qa_report.get("pages"),
            layout_warnings=len(layout_warnings),
            fidelity_soft_warnings=len(soft),
            pdf=str(layout.pdf),
        )
        (workdir / "structured.json").write_text(json.dumps(structured, ensure_ascii=False, indent=1))
    except Exception as exc:  # noqa: BLE001 - a failing case is a data point
        result.update(status="failed", error_category=classify_structuring_error(exc)["category"],
                      error=f"{type(exc).__name__}: {str(exc)[:160]}")
    finally:
        llm_backend.usage_observer = None
    result["duration_s"] = round(time.perf_counter() - start, 1)
    result["cost_usd"] = round(sum(float(u.get("cost") or 0) for u in usage), 5)
    result["calls"] = len(usage)
    result["providers"] = sorted({str(u.get("provider")) for u in usage})
    return result


def cmd_run(args) -> None:
    os.environ["WHUB_LLM_BACKEND"] = "openrouter"
    os.environ["WHUB_PRIMARY_MODEL"] = args.model
    os.environ["WHUB_FALLBACK_MODEL"] = ""
    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    cases = args.cases.split(",") if args.cases else list(CASES)
    with out.open("a") as handle:
        for case in cases:
            row = run_case(case, args.model, out.parent)
            handle.write(json.dumps(row, ensure_ascii=False) + "\n")
            handle.flush()
            print(json.dumps({k: row.get(k) for k in ("case", "status", "coverage", "exact_copy", "duration_s", "cost_usd", "error_category")}), flush=True)


def cmd_report(args) -> None:
    rows = [json.loads(line) for path in args.files for line in Path(path).read_text().splitlines() if line.strip()]
    by_model: dict[str, list[dict]] = {}
    for row in rows:
        by_model.setdefault(row["model"], []).append(row)

    def avg(values):
        values = [v for v in values if v is not None]
        return round(mean(values), 3) if values else None

    print("| Modèle | ready | draft | failed | couverture | copie exacte | alertes layout | durée moy. (s) | coût total ($) |")
    print("|---|---|---|---|---|---|---|---|---|")
    summary = []
    for model, items in by_model.items():
        statuses = [r["status"] for r in items]
        summary.append((
            -statuses.count("failed"), avg([r.get("coverage") for r in items]) or 0, model, items, statuses,
        ))
    for _neg_failed, _cov, model, items, statuses in sorted(summary, reverse=True):
        print(
            f"| {model} | {statuses.count('passed')} | {statuses.count('draft')} | {statuses.count('failed')} "
            f"| {avg([r.get('coverage') for r in items])} | {avg([r.get('exact_copy') for r in items])} "
            f"| {avg([r.get('layout_warnings') for r in items])} | {avg([r.get('duration_s') for r in items])} "
            f"| {round(sum(r.get('cost_usd') or 0 for r in items), 3)} |"
        )
    print("\nDétail par cas (statut / couverture / copie exacte / durée):\n")
    models = list(by_model)
    print("| Cas | " + " | ".join(models) + " |")
    print("|---|" + "---|" * len(models))
    for case in CASES:
        cells = []
        for model in models:
            row = next((r for r in by_model[model] if r["case"] == case), None)
            if row is None:
                cells.append("—")
            elif row["status"] == "failed":
                cells.append(f"❌ {row.get('error_category')}")
            else:
                cells.append(f"{row['status']} {row.get('coverage')}/{row.get('exact_copy')} {row['duration_s']}s")
        print(f"| {case} | " + " | ".join(cells) + " |")


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = parser.add_subparsers(dest="command", required=True)
    run = sub.add_parser("run")
    run.add_argument("--model", required=True)
    run.add_argument("--out", required=True)
    run.add_argument("--cases", default="")
    run.set_defaults(func=cmd_run)
    report = sub.add_parser("report")
    report.add_argument("files", nargs="+")
    report.set_defaults(func=cmd_report)
    args = parser.parse_args()
    args.func(args)


if __name__ == "__main__":
    main()
