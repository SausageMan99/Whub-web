#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import fitz
from PIL import Image, ImageDraw, ImageFont

ROOT = Path('/root/whub-cv-factory')
WORKER = ROOT / 'workers' / 'cv-worker'
sys.path.insert(0, str(WORKER))

from src.layout_packing import build_layout_packing_options, assert_packing_preserves_experience_content  # noqa: E402
from src.qa import QAError, collect_page_layout_metrics, run_qa  # noqa: E402
from src.rendering import render_pdf  # noqa: E402

RUN_ID = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
OUT = ROOT / 'artifacts' / 'sprint3' / f's3_5_multi_cv_smoke_{RUN_ID}'
OUT.mkdir(parents=True, exist_ok=True)

CASES = [
    {
        'id': 'zahia_like_location_and_role_facts',
        'kind': 'real_anonymized_s2_fixture',
        'input': ROOT / 'artifacts/s2_5_fidelity_smoke_20260531T185805Z/zahia_like_location_and_role_facts/input.json',
        'before_pdf': ROOT / 'artifacts/s2_5_fidelity_smoke_20260531T185805Z/zahia_like_location_and_role_facts/output.pdf',
    },
    {
        'id': 'oussama_like_rpa_copy_preservation',
        'kind': 'real_anonymized_s2_fixture',
        'input': ROOT / 'artifacts/s2_5_fidelity_smoke_20260531T185805Z/oussama_like_rpa_copy_preservation/input.json',
        'before_pdf': ROOT / 'artifacts/s2_5_fidelity_smoke_20260531T185805Z/oussama_like_rpa_copy_preservation/output.pdf',
    },
    {
        'id': 'thorez_like_realizations_and_tools_coverage',
        'kind': 'real_anonymized_s2_fixture',
        'input': ROOT / 'artifacts/s2_5_fidelity_smoke_20260531T185805Z/thorez_like_realizations_and_tools_coverage/input.json',
        'before_pdf': ROOT / 'artifacts/s2_5_fidelity_smoke_20260531T185805Z/thorez_like_realizations_and_tools_coverage/output.pdf',
    },
    {
        'id': 's3_4_zahia_oussama_like_heavy_layout',
        'kind': 'sprint3_heavy_layout_fixture',
        'input': ROOT / 'artifacts/sprint3/input_layout_retry.json',
        'before_pdf': ROOT / 'artifacts/sprint3/s3_4_zahia_oussama_like_smoke.pdf',
    },
]

CONTACT_MARKERS = {
    'email': re.compile(r'@'),
    'phone_fr': re.compile(r'(?<!\d)(?:\+33\s?|0)[67](?:[\s.\-]?\d{2}){4}(?!\d)'),
    'linkedin': re.compile(r'linkedin', re.I),
    'url': re.compile(r'https?://|www\.', re.I),
}


def clean_payload(data: dict[str, Any]) -> dict[str, Any]:
    cleaned = dict(data)
    cleaned.pop('_layout', None)
    return cleaned


def pdf_text(pdf: Path) -> str:
    with fitz.open(str(pdf)) as doc:
        return '\n'.join(page.get_text('text') for page in doc)


def normalize(text: str) -> str:
    return re.sub(r'\s+', ' ', text).strip().lower()


def flatten_source_items(value: Any) -> list[str]:
    out: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            if key.startswith('_'):
                continue
            out.extend(flatten_source_items(child))
    elif isinstance(value, list):
        for child in value:
            out.extend(flatten_source_items(child))
    elif isinstance(value, str):
        item = value.strip()
        if item and len(item) >= 3:
            out.append(item)
    return out


def source_coverage(data: dict[str, Any], text: str) -> dict[str, Any]:
    text_norm = normalize(text)
    checked = []
    missing = []
    seen = set()
    for item in flatten_source_items(data):
        item_norm = normalize(item)
        if item_norm in seen:
            continue
        seen.add(item_norm)
        checked.append(item)
        if item_norm not in text_norm:
            missing.append(item)
    return {'checked_items': len(checked), 'missing_count': len(missing), 'missing': missing[:25]}


def contacts(text: str) -> dict[str, bool]:
    return {name: bool(pattern.search(text)) for name, pattern in CONTACT_MARKERS.items()}


def metrics_for_pdf(pdf: Path) -> list[dict[str, Any]]:
    with fitz.open(str(pdf)) as doc:
        metrics = collect_page_layout_metrics(doc)
        safe = []
        for metric in metrics:
            safe.append({
                'page': int(metric.get('page', 0)),
                'char_count': int(metric.get('char_count', 0)),
                'block_count': int(metric.get('block_count', 0)),
                'used_ratio': round(float(metric.get('used_ratio', 0)), 3),
                'blank_after_pt': round(float(metric.get('blank_after_pt', 0)), 1),
                'starts_with_suite': bool(metric.get('starts_with_suite', False)),
                'has_experience_heading': bool(metric.get('has_experience_heading', False)),
            })
        return safe


def qa_for_pdf(pdf: Path, data: dict[str, Any]) -> dict[str, Any]:
    try:
        report = run_qa(pdf, structured_data=data)
        status = 'passed'
    except QAError as exc:
        report = exc.report
        status = 'failed'
    return {
        'status': status,
        'passed': bool(report.get('passed', False)),
        'pages': int(report.get('pages', 0)),
        'layout_issues': report.get('layout_issues', []),
        'human_taste': report.get('human_taste', {}),
        'contact_hits': report.get('contact_hits', []),
        'bad_glyphs': bool(report.get('bad_glyphs', False)),
        'content_integrity_issues': report.get('content_integrity_issues', []),
        'text_overflow_hits': report.get('text_overflow_hits', []),
        'has_logo': bool(report.get('has_logo', False)),
        'has_watermark': bool(report.get('has_watermark', False)),
        'layout_metrics': report.get('layout_metrics', metrics_for_pdf(pdf)),
    }


def render_page_thumb(pdf: Path, page_index: int, width: int = 360) -> Image.Image:
    with fitz.open(str(pdf)) as doc:
        page = doc.load_page(page_index)
        zoom = width / page.rect.width
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom), alpha=False)
        return Image.frombytes('RGB', [pix.width, pix.height], pix.samples)


def make_case_montage(case_results: list[dict[str, Any]]) -> Path:
    tiles = []
    for case in case_results:
        pdf = Path(case['current_pdf'])
        with fitz.open(str(pdf)) as doc:
            page_indexes = [0] if doc.page_count == 1 else [0, doc.page_count - 1]
        for page_index in page_indexes:
            thumb = render_page_thumb(pdf, page_index)
            label = f"{case['id']} — page {page_index + 1}"
            label_h = 34
            tile = Image.new('RGB', (thumb.width, thumb.height + label_h), 'white')
            tile.paste(thumb, (0, label_h))
            draw = ImageDraw.Draw(tile)
            draw.text((8, 8), label, fill=(35, 29, 25))
            tiles.append(tile)
    if not tiles:
        raise RuntimeError('no montage tiles')
    columns = 2
    pad = 24
    tile_w = max(tile.width for tile in tiles)
    tile_h = max(tile.height for tile in tiles)
    rows = (len(tiles) + columns - 1) // columns
    canvas = Image.new('RGB', (columns * tile_w + (columns + 1) * pad, rows * tile_h + (rows + 1) * pad), (245, 240, 235))
    for i, tile in enumerate(tiles):
        x = pad + (i % columns) * (tile_w + pad)
        y = pad + (i // columns) * (tile_h + pad)
        canvas.paste(tile, (x, y))
    montage = OUT / 's3_5_current_pdfs_first_last_montage.png'
    canvas.save(montage)
    return montage


results = []
for case in CASES:
    data = clean_payload(json.loads(case['input'].read_text(encoding='utf-8')))
    case_dir = OUT / case['id']
    case_dir.mkdir(parents=True, exist_ok=True)
    (case_dir / 'input.json').write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')

    layout_options = build_layout_packing_options(data)
    payload = dict(data)
    payload['_layout'] = layout_options
    assert_packing_preserves_experience_content(data, payload)
    (case_dir / 'layout_options.json').write_text(json.dumps(layout_options, ensure_ascii=False, indent=2), encoding='utf-8')

    pdf = render_pdf(data, case_dir, layout_options=layout_options, output_name='current_layout_intelligence.pdf')
    text = pdf_text(pdf)
    current_qa = qa_for_pdf(pdf, data)
    current_metrics = metrics_for_pdf(pdf)
    coverage = source_coverage(data, text)
    contact_markers = contacts(text)
    hard_failures = []
    if not current_qa['passed']:
        hard_failures.append('qa_failed')
    if any(contact_markers.values()) or current_qa['contact_hits']:
        hard_failures.append('contact_marker')
    if current_qa['bad_glyphs']:
        hard_failures.append('bad_glyph')
    if coverage['missing_count']:
        hard_failures.append('source_coverage_missing')

    before = None
    before_pdf = case.get('before_pdf')
    if before_pdf and before_pdf.exists():
        before_qa = qa_for_pdf(before_pdf, data)
        before = {
            'pdf': str(before_pdf),
            'qa': before_qa,
            'metrics': metrics_for_pdf(before_pdf),
            'file_copied_to': str(case_dir / 'before_existing.pdf'),
        }
        shutil.copy2(before_pdf, case_dir / 'before_existing.pdf')

    result = {
        'id': case['id'],
        'kind': case['kind'],
        'input': str(case_dir / 'input.json'),
        'current_pdf': str(pdf),
        'layout_options': layout_options,
        'current_qa': current_qa,
        'current_metrics': current_metrics,
        'source_coverage': coverage,
        'contact_markers': contact_markers,
        'before': before,
        'comparison': {
            'pages_before': before['qa']['pages'] if before else None,
            'pages_after': current_qa['pages'],
            'score_before': before['qa'].get('human_taste', {}).get('score') if before else None,
            'score_after': current_qa.get('human_taste', {}).get('score'),
            'layout_issues_before': before['qa'].get('layout_issues', []) if before else None,
            'layout_issues_after': current_qa.get('layout_issues', []),
        },
        'hard_failures': hard_failures,
    }
    (case_dir / 'qa_report.json').write_text(json.dumps(current_qa, ensure_ascii=False, indent=2), encoding='utf-8')
    (case_dir / 'layout_metrics.json').write_text(json.dumps(current_metrics, ensure_ascii=False, indent=2), encoding='utf-8')
    (case_dir / 'source_coverage.json').write_text(json.dumps(coverage, ensure_ascii=False, indent=2), encoding='utf-8')
    results.append(result)

montage = make_case_montage(results)
ledger = {
    'run_id': RUN_ID,
    'generated_at_utc': datetime.now(timezone.utc).isoformat(),
    'scope': 'S3-5 evidence ledger + local multi-CV smoke, no prod/push/restart/deploy',
    'case_count': len(results),
    'cases_passed': sum(1 for r in results if not r['hard_failures']),
    'cases_failed': [r['id'] for r in results if r['hard_failures']],
    'artifacts_dir': str(OUT),
    'montage': str(montage),
    'cases': results,
    'non_prod_guards': {
        'push': False,
        'worker_restart': False,
        'vercel_deploy': False,
    },
}
(OUT / 'evidence_ledger.json').write_text(json.dumps(ledger, ensure_ascii=False, indent=2), encoding='utf-8')

summary_lines = [
    '# S3-5 Evidence ledger — multi-CV local smoke',
    '',
    f"Run: `{RUN_ID}`",
    f"Artifacts: `{OUT}`",
    f"Montage: `{montage}`",
    '',
    '| Case | Type | QA | Pages before→after | Taste before→after | Coverage | Layout issues after |',
    '|---|---|---:|---:|---:|---:|---|',
]
for r in results:
    qa = 'GO' if not r['hard_failures'] else 'NO-GO ' + ','.join(r['hard_failures'])
    comp = r['comparison']
    before_pages = comp['pages_before'] if comp['pages_before'] is not None else 'n/a'
    before_score = comp['score_before'] if comp['score_before'] is not None else 'n/a'
    score_after = comp['score_after'] if comp['score_after'] is not None else 'n/a'
    coverage = r['source_coverage']
    summary_lines.append(
        f"| {r['id']} | {r['kind']} | {qa} | {before_pages}→{comp['pages_after']} | {before_score}→{score_after} | {coverage['checked_items']} checked / {coverage['missing_count']} missing | {json.dumps(comp['layout_issues_after'], ensure_ascii=False)} |"
    )
summary_lines.extend([
    '',
    'No prod action performed: no push, no whub-cv-worker.service restart, no Vercel deploy.',
])
(OUT / 'README.md').write_text('\n'.join(summary_lines) + '\n', encoding='utf-8')

print(json.dumps({
    'run_id': RUN_ID,
    'artifacts_dir': str(OUT),
    'ledger': str(OUT / 'evidence_ledger.json'),
    'readme': str(OUT / 'README.md'),
    'montage': str(montage),
    'cases_passed': ledger['cases_passed'],
    'cases_failed': ledger['cases_failed'],
}, ensure_ascii=False, indent=2))
if ledger['cases_failed']:
    sys.exit(1)
