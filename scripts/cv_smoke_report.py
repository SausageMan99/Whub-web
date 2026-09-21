#!/usr/bin/env python3
"""Rapport du banc smoke CV Factory — généré depuis scripts/cv_smoke_results.jsonl.

Usage:
  python scripts/cv_smoke_report.py           # affiche le rapport
  python scripts/cv_smoke_report.py --write   # écrit aussi ops/cv-smoke-baseline-<date>.jsonl + .md

Baseline du 2026-09-21 : à rejouer après chaque correction (étape 1) pour
comparaison avant/après.
"""
import json
import shutil
import sys
from pathlib import Path

REPO = Path("/root/whub-cv-factory")
RESULTS = REPO / "scripts/cv_smoke_results.jsonl"
OPS_STEM = REPO / "ops/cv-smoke-baseline-2026-09-21"

# Avant correctif : les trois fixtures issues des pannes de septembre DOIVENT
# échouer (elles prouvent les pannes). Elles passeront après l'étape 1.
EXPECTED_DURING_BASELINE = {
    "benjamin": "fail",
    "noel": "fail",
    "yannick": "fail",
}
TERMINAL_OK = {"ready", "draft_ready"}


def fmt_dur(d):
    return f"{d:.0f}" if isinstance(d, (int, float)) else "—"


def main() -> int:
    if not RESULTS.exists():
        print(f"Introuvable: {RESULTS}")
        return 1
    rows = [json.loads(l) for l in RESULTS.read_text().splitlines() if l.strip()]

    out = []
    out.append("# Baseline banc smoke CV Factory — 2026-09-21")
    out.append("")
    out.append("Worker : code du working tree (commit 38eb786 + fichiers non commités), modèle google/gemini-2.5-flash via openrouter.")
    out.append("")
    out.append("| Cas | Statut | Attendu (avant fix) | Durée (s) | Version | QA | Scores (layout/global/fidélité) | Alertes douces | Verdict |")
    out.append("|---|---|---|---|---|---|---|---|---|")

    n_pass = n_fail = 0
    surprises = []
    for r in rows:
        case = r.get("case", "?")
        status = r.get("status") or "?"
        sc = r.get("scores") or {}
        scores = "/".join(str(sc.get(k, "—")) for k in ("layout", "overall", "fidelity")) if sc else "—"
        warns = r.get("soft_warnings") or []
        exp = EXPECTED_DURING_BASELINE.get(case, "pass")
        actual = "pass" if status in TERMINAL_OK else "fail"
        if actual == "pass":
            n_pass += 1
        else:
            n_fail += 1
        verdict = "✅ attendu" if actual == exp else "⚠️ INATTENDU"
        if actual != exp:
            surprises.append((case, status, exp))
        out.append(
            f"| {case} | {status} | {exp} | {fmt_dur(r.get('duration_seconds'))} | "
            f"{r.get('version') or '—'} | {r.get('qa_status') or '—'} | {scores} | "
            f"{len(warns)} | {verdict} |"
        )

    out.append("")
    out.append(f"**Réussis : {n_pass} — Échoués : {n_fail} — Cas enregistrés : {len(rows)}/11**")
    if surprises:
        out.append("")
        out.append("Écarts par rapport aux attentes pré-correctif :")
        for case, status, exp in surprises:
            out.append(f"- {case}: {status} (attendu {exp})")
    text = "\n".join(out) + "\n"

    print(text)
    if "--write" in sys.argv:
        shutil.copyfile(RESULTS, OPS_STEM.with_suffix(".jsonl"))
        OPS_STEM.with_suffix(".md").write_text(text)
        print(f"[écrit] {OPS_STEM}.jsonl + .md")
    return 0


if __name__ == "__main__":
    sys.exit(main())
