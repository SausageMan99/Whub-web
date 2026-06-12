#!/usr/bin/env python3
"""W hub CV Factory — incident quality loop.

Fetches recent failed / blocked CV generations from Supabase, classifies the
failure signature from cv_requests + cv_events, proposes concrete engineering
fixes, and appends a redacted history entry.

This script is deliberately read-only against Supabase. It does not retry jobs,
modify code, commit, push, deploy, or restart the worker. It is safe to run from
cron and to send its output to Telegram.
"""
from __future__ import annotations

import argparse
import datetime as dt
import json
import os
import sys
import textwrap
import urllib.parse
import urllib.request
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
DEFAULT_ENV = ROOT / ".env"
DEFAULT_HISTORY = ROOT / "ops" / "cv-quality-history.jsonl"
DEFAULT_REPORT = ROOT / "ops" / "cv-quality-latest.md"
BLOCKED_STATUSES = {"failed", "qa_failed", "dead_letter", "needs_human_review"}


def _load_env(path: Path) -> dict[str, str]:
    env: dict[str, str] = {}
    if not path.exists():
        raise SystemExit(f"Missing env file: {path}")
    for raw in path.read_text().splitlines():
        line = raw.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        key, value = line.split("=", 1)
        value = value.strip().strip('"').strip("'").rstrip(",")
        env[key.strip()] = value
    return env


class SupabaseRest:
    def __init__(self, url: str, key: str) -> None:
        self.url = url.rstrip("/")
        self.headers = {
            "apikey": key,
            "Authorization": f"Bearer {key}",
            "Accept": "application/json",
            "Prefer": "return=representation",
        }

    def get(self, table: str, query: dict[str, str]) -> list[dict[str, Any]]:
        encoded = urllib.parse.urlencode(query, safe="(),.:*")
        req = urllib.request.Request(f"{self.url}/rest/v1/{table}?{encoded}", headers=self.headers)
        with urllib.request.urlopen(req, timeout=45) as response:
            payload = response.read().decode("utf-8")
        data = json.loads(payload or "[]")
        if isinstance(data, dict):
            return [data]
        return data


def _terminal_event(events: list[dict[str, Any]]) -> dict[str, Any] | None:
    for event in reversed(events):
        if event.get("event_type") in {"failed", "qa_failed", "dead_letter", "needs_human_review", "ready", "draft_ready"}:
            return event
    return events[-1] if events else None


def _event_payload(events: list[dict[str, Any]], event_type: str) -> dict[str, Any]:
    for event in events:
        if event.get("event_type") == event_type:
            payload = event.get("payload") or {}
            return payload if isinstance(payload, dict) else {}
    return {}


def _safe_request(row: dict[str, Any], events: list[dict[str, Any]]) -> dict[str, Any]:
    terminal = _terminal_event(events) or {}
    terminal_payload = terminal.get("payload") or {}
    if not isinstance(terminal_payload, dict):
        terminal_payload = {}
    quality = _event_payload(events, "quality_source_profiled")
    source_profile = quality.get("source_profile")
    fidelity_issues = terminal_payload.get("fidelity_issues") or []
    if not isinstance(fidelity_issues, list):
        fidelity_issues = [str(fidelity_issues)]
    return {
        "request_id": row.get("id"),
        "request_id_prefix": str(row.get("id", ""))[:8],
        "created_at": row.get("created_at"),
        "status": row.get("status"),
        "worker_attempts": row.get("worker_attempts"),
        "candidate_first_name_present": bool(str(row.get("candidate_first_name") or "").strip()),
        "last_error_signature": str(row.get("last_error") or "")[:80],
        "error_category": terminal_payload.get("error_category"),
        "fidelity_issues": fidelity_issues[:5],
        "source_profile": source_profile,
        "event_sequence": [event.get("event_type") for event in events],
        "stage_boundary": " → ".join(str(event.get("event_type")) for event in events),
        "extracted_chars": _event_payload(events, "extraction_done").get("chars"),
        "sanitized_chars": _event_payload(events, "source_sanitized").get("sanitized_chars"),
    }


def _signature(safe: dict[str, Any]) -> str:
    issue = "+".join(safe.get("fidelity_issues") or []) or "no_specific_issue"
    category = safe.get("error_category") or "no_category"
    profile = safe.get("source_profile") or "unknown_profile"
    first = "first_name_present" if safe.get("candidate_first_name_present") else "missing_first_name"
    return f"{safe.get('status')}|{category}|{issue}|{profile}|{first}"


def _recommendations(safe: dict[str, Any]) -> list[dict[str, Any]]:
    category = safe.get("error_category")
    issues = set(safe.get("fidelity_issues") or [])
    profile = safe.get("source_profile")
    missing_first = not safe.get("candidate_first_name_present")
    recs: list[dict[str, Any]] = []

    if missing_first:
        recs.append({
            "priority": "P0",
            "title": "Refuser les créations sans prénom candidat côté portail",
            "diagnostic": "cv_requests.candidate_first_name est vide. Sans prénom, le worker perd son repère d'anonymisation et les contrôles de fidélité/identité deviennent moins fiables.",
            "fix": "Dans apps/web/app/requests/new/actions.ts, valider candidate_first_name.trim() avant insert. Retourner un code UI explicite missing_candidate_first_name. Ajouter un test server action + un test UI si le formulaire expose le champ.",
            "files": ["apps/web/app/requests/new/actions.ts", "apps/web/tests/*request*.test.ts"],
            "verification": "Créer une demande sans prénom doit échouer avant cv_requests; une demande avec prénom doit créer une row submitted.",
        })

    if category == "source_fidelity" and "source_coverage_missing_experience_item" in issues:
        recs.append({
            "priority": "P0",
            "title": "Ajouter une réparation structurante pour expérience source manquante",
            "diagnostic": "La génération passe extraction + sanitization + profiling puis échoue car une expérience présente dans le CV source n'est pas couverte dans le JSON structuré.",
            "fix": "Ajouter un test fixture anonymisé reproduisant le CV senior_long. Renforcer la structuring QA pour lister les blocs expérience manquants par index redacted, puis ajouter un retry ciblé: si source_coverage_missing_experience_item, relancer uniquement la structuration avec consigne 'preserve all experience blocks' ou réparer le JSON en réinjectant le bloc manquant sans réécrire le reste.",
            "files": ["workers/cv-worker/src/structuring.py", "workers/cv-worker/src/qa.py", "workers/cv-worker/tests/test_structuring*.py", "workers/cv-worker/tests/test_qa.py"],
            "verification": "Le fixture doit finir en ready/draft_ready ou échouer avec un diagnostic plus précis; aucun contact/surnom ne doit apparaître; verify_quality_loop.sh doit rester vert.",
        })

    if category == "contact_leak":
        recs.append({
            "priority": "P0",
            "title": "Classifier le contact leak par chemin JSON redacted avant de bloquer",
            "diagnostic": "Le pipeline bloque sur coordonnées. Il faut distinguer vrai contact candidat vs faux positif type Th@Bot / texte source légitime.",
            "fix": "Persister uniquement catégorie + chemin JSON redacted + type de marqueur, jamais la valeur brute. Auto-sanitizer les emails/téléphones/URLs résiduels, garder hard block si valeur candidate réelle.",
            "files": ["workers/cv-worker/src/qa.py", "workers/cv-worker/src/source_sanitizer.py", "workers/cv-worker/tests/test_qa.py"],
            "verification": "Tests contact réel bloqué, faux positif source-faithful nettoyé, aucun raw contact en cv_events.",
        })

    if category == "transient_model_failure":
        recs.append({
            "priority": "P1",
            "title": "Séparer timeout modèle, erreur pré-modèle et JSON invalide",
            "diagnostic": "transient_model_failure est un bucket trop large. Il masque parfois NUL bytes, argv trop long, timeout OpenRouter ou erreur Hermes CLI.",
            "fix": "Dans structuring runner/main, classifier avant fail_job: pre_model_subprocess_error, model_timeout, model_nonzero_exit, invalid_json. Garder last_error safe.",
            "files": ["workers/cv-worker/src/main.py", "workers/cv-worker/src/structuring.py", "workers/cv-worker/tests/test_main_error_taxonomy.py"],
            "verification": "Un test par bucket; cv_events.payload.error_category stable et sans stack brute.",
        })

    if safe.get("status") == "needs_human_review" or profile == "scanned":
        recs.append({
            "priority": "P1",
            "title": "Créer un chemin review humain clair pour sources low-confidence",
            "diagnostic": "Le CV est trop faible/scanné pour générer automatiquement sans risque de perte d'information.",
            "fix": "UI: afficher besoin d'OCR/review + action relancer après correction. Worker: ne pas transformer ça en failed; garder needs_human_review final avec raison redacted.",
            "files": ["apps/web/lib/request-detail-ui.ts", "workers/cv-worker/src/quality_report.py"],
            "verification": "Source scannée courte finit en needs_human_review, pas failed.",
        })

    if not recs:
        recs.append({
            "priority": "P2",
            "title": "Créer une fiche incident et un fixture anonymisé avant patch",
            "diagnostic": "La signature n'a pas encore de playbook fiable. Ne pas patcher à l'aveugle.",
            "fix": "Télécharger la source, extraire un fixture anonymisé minimal, écrire un test rouge qui reproduit l'échec, puis seulement patcher le module concerné.",
            "files": ["workers/cv-worker/tests/fixtures/", "workers/cv-worker/tests/"],
            "verification": "Test rouge avant fix, vert après fix; aucun changement large hors module ciblé.",
        })

    return recs


def _fetch_incidents(client: SupabaseRest, days: int, limit: int, request_prefix: str | None) -> list[dict[str, Any]]:
    since = (dt.datetime.now(dt.timezone.utc) - dt.timedelta(days=days)).isoformat()
    rows = client.get("cv_requests", {
        "select": "id,created_at,status,last_error,worker_attempts,candidate_first_name,title,source_file_name",
        "created_at": f"gte.{since}",
        "order": "created_at.desc",
        "limit": str(limit),
    })
    if request_prefix:
        rows = [row for row in rows if str(row.get("id", "")).startswith(request_prefix)]
    rows = [row for row in rows if row.get("status") in BLOCKED_STATUSES]
    incidents: list[dict[str, Any]] = []
    for row in rows:
        rid = row.get("id")
        if not rid:
            continue
        events = client.get("cv_events", {
            "select": "event_type,payload,created_at",
            "request_id": f"eq.{rid}",
            "order": "created_at.asc",
        })
        safe = _safe_request(row, events)
        safe["signature"] = _signature(safe)
        safe["recommendations"] = _recommendations(safe)
        incidents.append(safe)
    return incidents


def _write_history(incidents: list[dict[str, Any]], history_path: Path) -> None:
    history_path.parent.mkdir(parents=True, exist_ok=True)
    now = dt.datetime.now(dt.timezone.utc).isoformat()
    existing_keys: set[str] = set()
    if history_path.exists():
        for line in history_path.read_text().splitlines():
            if not line.strip():
                continue
            try:
                item = json.loads(line)
            except json.JSONDecodeError:
                continue
            existing_keys.add(f"{item.get('request_id_prefix')}|{item.get('signature')}")
    with history_path.open("a", encoding="utf-8") as fh:
        for incident in incidents:
            key = f"{incident.get('request_id_prefix')}|{incident.get('signature')}"
            if key in existing_keys:
                continue
            record = {k: v for k, v in incident.items() if k != "request_id"}
            record["recorded_at"] = now
            fh.write(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n")


def _format_report(incidents: list[dict[str, Any]], days: int) -> str:
    now = dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
    lines = [
        "# W hub CV Factory — boucle qualité incidents",
        "",
        f"Fenêtre analysée: {days} jour(s)",
        f"Généré: {now}",
        "",
    ]
    if not incidents:
        lines.append("Aucun incident bloquant trouvé sur la fenêtre.")
        return "\n".join(lines) + "\n"

    lines.append(f"Incidents bloquants: {len(incidents)}")
    by_signature = Counter(item["signature"] for item in incidents)
    lines.append("\n## Signatures")
    for signature, count in by_signature.most_common():
        lines.append(f"- {count}× `{signature}`")

    grouped: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for incident in incidents:
        grouped[incident["signature"]].append(incident)

    lines.append("\n## Diagnostics et fixes proposés")
    for signature, group in grouped.items():
        sample = group[0]
        lines.extend([
            "",
            f"### `{signature}`",
            f"Occurrences: {len(group)}",
            f"Exemple request: `{sample['request_id_prefix']}`",
            f"Stage boundary: `{sample['stage_boundary']}`",
            f"Chars: extraction={sample.get('extracted_chars')} / sanitized={sample.get('sanitized_chars')}",
        ])
        for rec in sample["recommendations"]:
            wrapped_diag = textwrap.fill(rec["diagnostic"], width=100)
            wrapped_fix = textwrap.fill(rec["fix"], width=100)
            wrapped_verif = textwrap.fill(rec["verification"], width=100)
            lines.extend([
                f"- {rec['priority']} — {rec['title']}",
                f"  Diagnostic: {wrapped_diag}",
                f"  Fix: {wrapped_fix}",
                f"  Fichiers: {', '.join(rec['files'])}",
                f"  Vérification: {wrapped_verif}",
            ])

    lines.extend([
        "",
        "## Garde-fou",
        "Ce rapport est read-only. Un patch doit suivre: fixture anonymisé → test rouge → correction ciblée → verify_quality_loop.sh → review → commit/push/restart si validé.",
    ])
    return "\n".join(lines) + "\n"


def main() -> int:
    parser = argparse.ArgumentParser(description="Diagnose W hub CV Factory failed generations and propose code fixes.")
    parser.add_argument("--days", type=int, default=7)
    parser.add_argument("--limit", type=int, default=100)
    parser.add_argument("--request-prefix")
    parser.add_argument("--env", type=Path, default=DEFAULT_ENV)
    parser.add_argument("--history", type=Path, default=DEFAULT_HISTORY)
    parser.add_argument("--report", type=Path, default=DEFAULT_REPORT)
    parser.add_argument("--no-history", action="store_true")
    parser.add_argument("--exit-zero", action="store_true", help="Always exit 0; useful for scheduled reports.")
    args = parser.parse_args()

    env = _load_env(args.env)
    url = env.get("SUPABASE_URL")
    key = env.get("SUPABASE_SERVICE_ROLE_KEY")
    if not url or not key:
        raise SystemExit("SUPABASE_URL or SUPABASE_SERVICE_ROLE_KEY missing from env")
    client = SupabaseRest(url, key)
    incidents = _fetch_incidents(client, args.days, args.limit, args.request_prefix)
    report = _format_report(incidents, args.days)
    args.report.parent.mkdir(parents=True, exist_ok=True)
    args.report.write_text(report, encoding="utf-8")
    if not args.no_history:
        _write_history(incidents, args.history)
    print(report)
    if args.exit_zero:
        return 0
    return 1 if incidents else 0


if __name__ == "__main__":
    raise SystemExit(main())
