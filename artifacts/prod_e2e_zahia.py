#!/usr/bin/env python3
import json
import os
import re
import sys
import time
import uuid
import hashlib
from datetime import datetime, timezone
from pathlib import Path

import requests

REPO = Path('/root/whub-cv-factory')
ENV_PATHS = [REPO / '.env', REPO / 'workers/cv-worker/.env']
SOURCE_PDF = Path('/root/.hermes/cache/documents/doc_4f504753d96d_Zahia Aris.pdf')
SOURCE_SHA256 = 'a2624097e140459f66c2e7c28dcf69a7d2bc763418f7ff5117ca12ddc028d1f5'
PROD_URL = 'https://web-topaz-zeta-hpye9vj4d1.vercel.app'
ADMIN_EMAIL = 'cdubosq@whub.fr'


def load_env():
    env = {}
    for path in ENV_PATHS:
        if not path.exists():
            continue
        for raw in path.read_text().splitlines():
            line = raw.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, val = line.split('=', 1)
            val = val.strip().strip('"').strip("'")
            env.setdefault(key.strip(), val)
    return env


def require_env(env, key):
    val = env.get(key) or os.environ.get(key)
    if not val:
        raise RuntimeError(f'missing env {key}')
    return val


def headers(key):
    return {
        'apikey': key,
        'Authorization': f'Bearer {key}',
        'Content-Type': 'application/json',
    }


def rest_get(base, key, table, params):
    r = requests.get(f'{base}/rest/v1/{table}', headers=headers(key), params=params, timeout=30)
    if not r.ok:
        raise RuntimeError(f'GET {table} failed HTTP {r.status_code}: {r.text[:300]}')
    return r.json()


def rest_post(base, key, table, payload):
    h = headers(key) | {'Prefer': 'return=representation'}
    r = requests.post(f'{base}/rest/v1/{table}', headers=h, data=json.dumps(payload), timeout=30)
    if not r.ok:
        raise RuntimeError(f'POST {table} failed HTTP {r.status_code}: {r.text[:500]}')
    return r.json()


def upload_storage(base, key, bucket, object_path, data, content_type):
    url = f'{base}/storage/v1/object/{bucket}/{object_path}'
    h = {'apikey': key, 'Authorization': f'Bearer {key}', 'Content-Type': content_type, 'x-upsert': 'false'}
    r = requests.post(url, headers=h, data=data, timeout=60)
    if not r.ok:
        raise RuntimeError(f'upload failed HTTP {r.status_code}: {r.text[:500]}')


def download_storage(base, key, bucket, object_path):
    url = f'{base}/storage/v1/object/{bucket}/{object_path}'
    h = {'apikey': key, 'Authorization': f'Bearer {key}'}
    r = requests.get(url, headers=h, timeout=60)
    if not r.ok:
        raise RuntimeError(f'download {bucket}/{object_path} failed HTTP {r.status_code}: {r.text[:300]}')
    return r.content


def extract_pdf_text(pdf_path):
    import fitz
    doc = fitz.open(pdf_path)
    return '\n'.join(str(page.get_text()) for page in doc)


def main():
    env = load_env()
    base = require_env(env, 'SUPABASE_URL').rstrip('/')
    key = require_env(env, 'SUPABASE_SERVICE_ROLE_KEY')
    sources_bucket = env.get('CV_SOURCES_BUCKET', 'cv-sources')
    finals_bucket = env.get('CV_FINALS_BUCKET', 'cv-finals')

    if not SOURCE_PDF.exists():
        raise RuntimeError(f'source pdf missing: {SOURCE_PDF}')
    actual_hash = hashlib.sha256(SOURCE_PDF.read_bytes()).hexdigest()
    if actual_hash != SOURCE_SHA256:
        raise RuntimeError(f'source sha mismatch: {actual_hash}')

    outdir = REPO / 'artifacts' / f'prod_e2e_zahia_{datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")}'
    outdir.mkdir(parents=True, exist_ok=True)

    # Lightweight deployed web smoke: confirms prod responds before DB/API E2E.
    login_res = requests.get(f'{PROD_URL}/login', timeout=30)
    requests_new_res = requests.get(f'{PROD_URL}/requests/new', allow_redirects=False, timeout=30)

    profiles = rest_get(base, key, 'profiles', {'select': 'id,email,role', 'email': f'eq.{ADMIN_EMAIL}', 'limit': '1'})
    if not profiles:
        raise RuntimeError(f'no existing profile for {ADMIN_EMAIL}; cannot create request with real user owner')
    profile = profiles[0]

    request_id = str(uuid.uuid4())
    source_file_name = 'Zahia_Aris_source_E2E.pdf'
    source_path = f'{request_id}/source/{source_file_name}'
    upload_storage(base, key, sources_bucket, source_path, SOURCE_PDF.read_bytes(), 'application/pdf')

    request_payload = {
        'id': request_id,
        'created_by': profile['id'],
        'title': 'E2E prod Zahia — CV W hub fidèle',
        'candidate_first_name': 'ZAHIA ARIS',
        'source_file_path': source_path,
        'source_file_name': source_file_name,
        'source_file_mime': 'application/pdf',
        'source_file_size': SOURCE_PDF.stat().st_size,
        'instructions': 'CV standard W hub fidèle. Conserver les faits, dates, localisations et expériences importantes. Ne pas compacter sans nécessité. Sortie client-facing sans coordonnées candidat.',
        'priority': 'urgent',
        'status': 'submitted',
    }
    rest_post(base, key, 'cv_requests', request_payload)

    deadline = time.time() + 25 * 60
    last_status = None
    snapshots = []
    while time.time() < deadline:
        rows = rest_get(base, key, 'cv_requests', {'select': 'id,status,last_error,worker_attempts,current_version_id,updated_at,created_at,ready_at', 'id': f'eq.{request_id}', 'limit': '1'})
        if not rows:
            raise RuntimeError('created request disappeared')
        row = rows[0]
        snapshots.append({'ts': datetime.now(timezone.utc).isoformat(), **row})
        if row['status'] != last_status:
            print(f"status={row['status']} attempts={row.get('worker_attempts')}", flush=True)
            last_status = row['status']
        if row['status'] in ('ready', 'failed', 'qa_failed', 'cancelled', 'archived'):
            break
        time.sleep(10)
    else:
        raise RuntimeError('timeout waiting for worker completion')

    request_snapshot = snapshots[-1]
    events = rest_get(base, key, 'cv_events', {'select': 'event_type,payload,created_at', 'request_id': f'eq.{request_id}', 'order': 'created_at.asc'})
    versions = rest_get(base, key, 'cv_versions', {'select': '*', 'request_id': f'eq.{request_id}', 'order': 'version_number.desc', 'limit': '1'})

    (outdir / 'request_poll_snapshots.json').write_text(json.dumps(snapshots, indent=2, ensure_ascii=False))
    (outdir / 'request_snapshot.json').write_text(json.dumps(request_snapshot, indent=2, ensure_ascii=False))
    (outdir / 'events.json').write_text(json.dumps(events, indent=2, ensure_ascii=False))

    if request_snapshot['status'] != 'ready':
        (outdir / 'failure.json').write_text(json.dumps({'request': request_snapshot, 'events': events, 'versions': versions}, indent=2, ensure_ascii=False))
        raise RuntimeError(f"request ended {request_snapshot['status']} last_error={request_snapshot.get('last_error')}")
    if not versions:
        raise RuntimeError('ready request has no version')
    version = versions[0]
    (outdir / 'version.json').write_text(json.dumps(version, indent=2, ensure_ascii=False))
    (outdir / 'structured.json').write_text(json.dumps(version.get('structured_json'), indent=2, ensure_ascii=False))
    (outdir / 'qa_report.json').write_text(json.dumps(version.get('qa_report'), indent=2, ensure_ascii=False))

    final_path = version.get('final_pdf_path')
    if not final_path:
        raise RuntimeError('final_pdf_path missing')
    pdf_bytes = download_storage(base, key, finals_bucket, final_path)
    final_pdf = outdir / 'final_prod_e2e.pdf'
    final_pdf.write_bytes(pdf_bytes)

    text = extract_pdf_text(final_pdf)
    (outdir / 'pdf_text.txt').write_text(text, encoding='utf-8')

    checks = {}
    q = version.get('qa_report') or {}
    checks['qa_passed'] = q.get('passed') is True
    checks['qa_no_contacts'] = q.get('contact_hits') == []
    checks['qa_layout_ok'] = q.get('layout_issues') == []
    checks['qa_no_overflow'] = q.get('text_overflow_hits') == []
    checks['has_logo'] = q.get('has_logo') is True
    checks['has_watermark'] = q.get('has_watermark') is True
    upper = text.upper()
    checks['first_name_only'] = 'ZAHIA' in upper and 'ZAHIA ARIS' not in upper and not re.search(r'\bARIS\b', upper)
    checks['no_email'] = re.search(r'[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}', upper, flags=re.I) is None
    checks['no_phone_like'] = re.search(r'(?:\+33|0)\s*[1-9](?:[\s.\-]?\d{2}){4}', text) is None
    checks['no_url_linkedin'] = not re.search(r'https?://|www\.|linkedin', text, flags=re.I)
    for term in ['GROUPE KLESIA', 'ASSURONE', 'ENOVACOM', 'Montreuil (93)', 'Asnières (92)', 'Rueil-Malmaison (92)', 'Paris (75)', 'Saint-Ouen-l’Aumône (95)']:
        checks[f'contains_{term}'] = term in text
    checks['no_known_hallucination_gsmc'] = 'GSMC' not in upper
    checks['no_known_hallucination_mars_2026'] = 'MARS 2026' not in upper
    checks['klesia_a_ce_jour'] = ('à ce jour' in text or 'A CE JOUR' in upper) and 'KLESIA' in upper
    checks['pages'] = q.get('pages')
    checks['request_id'] = request_id
    checks['version_id'] = version.get('id')
    checks['final_pdf'] = str(final_pdf)
    checks['artifact_dir'] = str(outdir)
    checks['prod_login_http'] = login_res.status_code
    checks['prod_requests_new_http'] = requests_new_res.status_code
    checks['prod_requests_new_location'] = requests_new_res.headers.get('location')

    failed = [k for k, v in checks.items() if k.startswith('contains_') and v is not True]
    failed += [k for k in ['qa_passed','qa_no_contacts','qa_layout_ok','qa_no_overflow','has_logo','has_watermark','first_name_only','no_email','no_phone_like','no_url_linkedin','no_known_hallucination_gsmc','no_known_hallucination_mars_2026','klesia_a_ce_jour'] if checks.get(k) is not True]
    checks['failed_checks'] = failed
    (outdir / 'e2e_verification.json').write_text(json.dumps(checks, indent=2, ensure_ascii=False))

    print(json.dumps({
        'request_id': request_id,
        'status': request_snapshot['status'],
        'version_id': version.get('id'),
        'artifact_dir': str(outdir),
        'final_pdf': str(final_pdf),
        'qa_passed': checks['qa_passed'],
        'pages': checks['pages'],
        'failed_checks': failed,
        'prod_login_http': login_res.status_code,
        'prod_requests_new_http': requests_new_res.status_code,
        'prod_requests_new_location': requests_new_res.headers.get('location'),
    }, indent=2, ensure_ascii=False), flush=True)
    if failed:
        raise RuntimeError('verification failed: ' + ', '.join(failed))

if __name__ == '__main__':
    main()
