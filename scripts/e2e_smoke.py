"""End-to-end smoke test for the W hub CV Factory auto-evaluation loop.

Steps:
1. Upload a test PDF to the cv-sources bucket.
2. Insert a cv_requests row in submitted status pointing to it.
3. Poll cv_events until the worker emits quality_source_profiled.
4. Verify cv_versions.qa_report.quality_report is persisted.
5. Clean up: delete the test request and the uploaded file.
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import time
import urllib.request
import urllib.parse
from pathlib import Path

# Test-bank case -> directory mapping. Keys are the short CLI names
# consumed by scripts/cv_smoke_battery.py.
CASE_DIRS: dict[str, str] = {
    "oussama": "Oussama_RPA_copy_preservation",
    "zahia": "Zahia_location_and_role_facts",
    "thorez": "Thorez_realizations_and_tools_coverage",
    "dense": "Dense_skills_pagination",
    "sanitize": "Sanitizer_contact_strip",
    "hodard": "Hodard_continuity",
    "rayan": "Rayan_prod_e2e",
    "amina": "AMINA_QA_Salesforce",
}

CASE_FIRST_NAMES: dict[str, str] = {
    "oussama": "Oussama",
    "zahia": "Zahia",
    "thorez": "Nicolas",
    "dense": "Oussama",
    "sanitize": "Jean",
    "hodard": "Florian",
    "rayan": "Rayan",
    "amina": "Amina",
}


def load_env(path: Path) -> dict[str, str]:
    out: dict[str, str] = {}
    for line in path.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" in line:
            k, v = line.split("=", 1)
            out[k.strip()] = v.strip().strip('"')
    return out


def sb_request(method: str, url: str, key: str, body=None, content_type=None, binary=None, prefer: str | None = None):
    headers = {"apikey": key, "Authorization": f"Bearer {key}"}
    data = None
    if binary is not None:
        data = binary
        if content_type:
            headers["Content-Type"] = content_type
    elif body is not None:
        data = json.dumps(body).encode()
        headers["Content-Type"] = "application/json"
    if prefer:
        headers["Prefer"] = prefer
    req = urllib.request.Request(url, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=30) as r:
        raw = r.read()
        if not raw:
            return None
        return json.loads(raw) if raw[:1] in (b"{", b"[") else raw


def main() -> int:
    parser = argparse.ArgumentParser(description="W hub CV Factory E2E smoke")
    parser.add_argument("--case", default=None, help="Test-bank case key (e.g. oussama)")
    parser.add_argument("--label", default=None, help="Optional human label for the JSON payload")
    parser.add_argument("--no-cleanup", action="store_true", help="Keep request and uploaded source for debugging")
    args = parser.parse_args()

    here = Path(__file__).resolve().parents[1]
    env = load_env(here / "apps/web/.env.local")
    url = env["NEXT_PUBLIC_SUPABASE_URL"].rstrip("/")
    key = env["SUPABASE_SERVICE_ROLE_KEY"]
    print(f"[env] url={url} key_len={len(key)}")

    if args.case:
        case_dir = CASE_DIRS.get(args.case)
        if not case_dir:
            print(f"unknown --case {args.case!r}; valid: {sorted(CASE_DIRS)}")
            return 1
        pdf = here / "cv_test_bank" / case_dir / "input.pdf"
        label = args.label or case_dir
        candidate_first_name = CASE_FIRST_NAMES[args.case]
    else:
        pdf = here / "cv_olivier_input/cv_olivier_v1.pdf"
        label = args.label or "olivier_default"
        candidate_first_name = "Smoke"

    if not pdf.exists():
        print(f"missing test pdf: {pdf}")
        return 1
    pdf_bytes = pdf.read_bytes()
    print(f"[case] {args.case or 'default'} label={label}")
    print(f"[pdf] {pdf.name} size={len(pdf_bytes)}")

    bucket = "cv-sources"
    object_path = f"smoke/quality_loop_{int(time.time())}.pdf"
    upload_url = f"{url}/storage/v1/object/{bucket}/{object_path}"
    print(f"[upload] {upload_url}")
    sb_request("POST", upload_url, key, binary=pdf_bytes, content_type="application/pdf")
    print("[upload] OK")

    # Create a cv_requests row in submitted status.
    row = {
        "status": "submitted",
        "instructions": f"auto-eval e2e smoke case={args.case or 'default'} label={label}. fait des controle de qualite, qu\'il n\'y est pas de saut de page injustifier, que la mise en page soit bonne. que le contenue soit bien fidel.",
        "candidate_first_name": candidate_first_name,
        "priority": "normal",
        "source_file_path": object_path,
        "source_file_name": pdf.name,
        "source_file_mime": "application/pdf",
        "source_file_size": len(pdf_bytes),
    }
    insert_url = f"{url}/rest/v1/cv_requests"
    created = sb_request("POST", insert_url, key, body=row, content_type="application/json", prefer="return=representation")
    if not isinstance(created, list) or not created:
        print(f"[insert] FAILED: {created!r}")
        return 1
    request_id = created[0]["id"]
    print(f"[insert] request_id={request_id}")

    # Poll cv_events for quality_source_profiled or terminal status.
    events_url = f"{url}/rest/v1/cv_events?request_id=eq.{request_id}&order=created_at.asc&select=event_type,payload,created_at"
    request_url = f"{url}/rest/v1/cv_requests?id=eq.{request_id}&select=id,status,last_error"
    versions_url = f"{url}/rest/v1/cv_versions?request_id=eq.{request_id}&select=id,version_number,qa_status,qa_report&order=version_number.desc&limit=1"

    deadline = time.time() + 300  # 5 min cap
    final_status = None
    quality_event_seen = False
    while time.time() < deadline:
        events = sb_request("GET", events_url, key) or []
        for ev in events:
            if ev.get("event_type") == "quality_source_profiled":
                quality_event_seen = True
        reqs = sb_request("GET", request_url, key) or []
        if reqs:
            final_status = reqs[0].get("status")
            if final_status in {"ready", "draft_ready", "qa_failed", "failed", "needs_human_review", "dead_letter"}:
                break
        time.sleep(5)

    print(f"\n[result] final_status={final_status}")
    print(f"[result] quality_source_profiled seen: {quality_event_seen}")

    versions = sb_request("GET", versions_url, key) or []
    payload: dict = {
        "label": label,
        "request_id": request_id,
        "status": final_status,
        "quality_event_seen": quality_event_seen,
    }
    if versions:
        v = versions[0]
        qr = (v.get("qa_report") or {}).get("quality_report")
        payload["version"] = v.get("version_number")
        payload["qa_status"] = v.get("qa_status")
        if qr:
            payload["qa_report_keys"] = sorted(qr.keys())
            payload["source_profile"] = qr.get("source_profile")
            payload["scores"] = qr.get("scores")
            payload["hard_blockers"] = qr.get("hard_blockers")
            payload["soft_warnings"] = qr.get("soft_warnings")
            payload["metrics"] = qr.get("metrics")
    else:
        payload["version"] = None
        payload["qa_status"] = None

    print(f"[JSON] {json.dumps(payload, ensure_ascii=False)}")

    # Cleanup
    if args.no_cleanup:
        print(f"[cleanup] SKIPPED request_id={request_id} object_path={object_path}")
    else:
        sb_request("DELETE", f"{url}/rest/v1/cv_requests?id=eq.{request_id}", key, prefer="return=representation")
        sb_request(
            "DELETE",
            f"{url}/storage/v1/object/{bucket}/{object_path}",
            key,
        )
        print("[cleanup] OK")

    return 0 if (quality_event_seen and final_status) else 1


if __name__ == "__main__":
    sys.exit(main())
