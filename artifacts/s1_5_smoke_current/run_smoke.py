#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

import fitz
from PIL import Image, ImageDraw

REPO = Path('/root/whub-cv-factory')
WORKER = REPO / 'workers' / 'cv-worker'
OUT_ROOT = REPO / 'artifacts' / ('s1_5_smoke_' + datetime.now().strftime('%Y%m%d_%H%M%S'))
RENDERER = WORKER / 'renderer' / 'whub_cv_renderer.py'
ASSETS = WORKER / 'assets' / 'whub'
FONTS = WORKER / 'assets' / 'fonts' / 'poppins'

CASES = [
    {
        'label': 'oussama',
        'input': WORKER / 'tests' / 'fixtures' / 'oussama_structured_faithful.json',
        'forbidden_names': [],
    },
    {
        'label': 'zahia',
        'input': REPO / 'artifacts' / 'zahia_faithful_regen' / 'structured_layout_render.json',
        'forbidden_names': [],
    },
]

sys.path.insert(0, str(WORKER))
from src.qa import QAError, collect_page_layout_metrics, run_qa  # noqa: E402


def scrub_report(report: dict) -> dict:
    clean = dict(report)
    # Avoid storing extracted text/snippets from candidate CVs in this summary.
    clean['layout_issues'] = [
        {k: v for k, v in issue.items() if k not in {'snippet', 'text'}}
        for issue in clean.get('layout_issues', [])
        if isinstance(issue, dict)
    ]
    clean['content_integrity_issues'] = [
        {k: v for k, v in issue.items() if k not in {'snippet', 'text', 'missing_fragment'}}
        if isinstance(issue, dict) else issue
        for issue in clean.get('content_integrity_issues', [])
    ]
    clean['text_overflow_hits'] = [
        {k: v for k, v in issue.items() if k not in {'text', 'snippet'}}
        if isinstance(issue, dict) else issue
        for issue in clean.get('text_overflow_hits', [])
    ]
    return clean


def safe_metrics(pdf_path: Path) -> list[dict]:
    doc = fitz.open(str(pdf_path))
    metrics = []
    for item in collect_page_layout_metrics(doc):
        metrics.append({
            'page': item['page'],
            'char_count': item['char_count'],
            'block_count': item['block_count'],
            'used_ratio': round(float(item['used_ratio']), 3),
            'blank_after_pt': round(float(item['blank_after_pt']), 1),
            'starts_with_suite': item['starts_with_suite'],
            'has_experience_heading': item['has_experience_heading'],
        })
    return metrics


def render_page_png(pdf_path: Path, page_index: int, png_path: Path) -> None:
    doc = fitz.open(str(pdf_path))
    page = doc[page_index]
    pix = page.get_pixmap(matrix=fitz.Matrix(1.25, 1.25), alpha=False)
    pix.save(str(png_path))


def make_montage(entries: list[dict], out_path: Path) -> None:
    thumbs = []
    for entry in entries:
        for key in ('first_page_png', 'last_page_png'):
            path = Path(entry[key])
            im = Image.open(path).convert('RGB')
            im.thumbnail((360, 520))
            canvas = Image.new('RGB', (380, 570), 'white')
            canvas.paste(im, ((380 - im.width) // 2, 35))
            draw = ImageDraw.Draw(canvas)
            draw.text((12, 10), f"{entry['label']} {key.replace('_page_png','')}", fill=(0, 0, 0))
            thumbs.append(canvas)
    if not thumbs:
        return
    cols = 2
    rows = (len(thumbs) + cols - 1) // cols
    montage = Image.new('RGB', (cols * 380, rows * 570), (245, 245, 245))
    for i, thumb in enumerate(thumbs):
        montage.paste(thumb, ((i % cols) * 380, (i // cols) * 570))
    montage.save(out_path)


def main() -> int:
    OUT_ROOT.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    env['WHUB_ASSETS_DIR'] = str(ASSETS)
    env['WHUB_FONTS_DIR'] = str(FONTS)
    cases_out = []
    for case in CASES:
        label = case['label']
        source = Path(case['input'])
        if not source.is_file():
            raise FileNotFoundError(f'missing input for {label}: {source}')
        out_dir = OUT_ROOT / label
        out_dir.mkdir(parents=True, exist_ok=True)
        input_copy = out_dir / 'input.json'
        shutil.copy2(source, input_copy)
        pdf_path = out_dir / f'{label}_repo_local.pdf'
        cmd = [sys.executable, str(RENDERER), str(input_copy), str(pdf_path)]
        proc = subprocess.run(cmd, cwd=str(REPO), env=env, text=True, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        if proc.returncode != 0:
            (out_dir / 'renderer_stderr.txt').write_text(proc.stderr, encoding='utf-8')
            raise RuntimeError(f'render failed for {label}, rc={proc.returncode}; stderr saved to {out_dir / "renderer_stderr.txt"}')
        structured = json.loads(input_copy.read_text(encoding='utf-8'))
        try:
            report = run_qa(pdf_path, forbidden_names=case.get('forbidden_names') or [], structured_data=structured)
            status = 'passed'
        except QAError as exc:
            report = exc.report
            status = 'failed'
        report = scrub_report(report)
        metrics = safe_metrics(pdf_path)
        first_png = out_dir / 'page_1.png'
        last_png = out_dir / f'page_{report.get("pages", 1)}.png'
        render_page_png(pdf_path, 0, first_png)
        if int(report.get('pages') or 0) > 1:
            render_page_png(pdf_path, int(report['pages']) - 1, last_png)
        else:
            shutil.copy2(first_png, last_png)
        (out_dir / 'qa_report.json').write_text(json.dumps(report, indent=2, ensure_ascii=False), encoding='utf-8')
        (out_dir / 'layout_metrics.json').write_text(json.dumps(metrics, indent=2, ensure_ascii=False), encoding='utf-8')
        layout_codes = [issue.get('code') for issue in report.get('layout_issues', []) if isinstance(issue, dict)]
        entry = {
            'label': label,
            'input': str(source),
            'pdf': str(pdf_path),
            'qa_report': str(out_dir / 'qa_report.json'),
            'layout_metrics': str(out_dir / 'layout_metrics.json'),
            'first_page_png': str(first_png),
            'last_page_png': str(last_png),
            'pages': report.get('pages'),
            'status': status,
            'passed': bool(report.get('passed')),
            'contact_hits': report.get('contact_hits'),
            'bad_glyphs': report.get('bad_glyphs'),
            'text_overflow_hits': report.get('text_overflow_hits'),
            'has_logo': report.get('has_logo'),
            'has_watermark': report.get('has_watermark'),
            'layout_issue_codes': layout_codes,
            'content_integrity_issue_count': len(report.get('content_integrity_issues') or []),
        }
        cases_out.append(entry)
    montage = OUT_ROOT / 'visual_montage_first_last.png'
    make_montage(cases_out, montage)
    summary = {
        'verdict': 'GO' if all(c['passed'] for c in cases_out) else 'NO_GO',
        'smoke_dir': str(OUT_ROOT),
        'renderer': str(RENDERER),
        'assets_dir': str(ASSETS),
        'fonts_dir': str(FONTS),
        'visual_montage': str(montage),
        'cases': cases_out,
        'no_prod_side_effects': True,
    }
    summary_path = OUT_ROOT / 'smoke_summary.json'
    summary_path.write_text(json.dumps(summary, indent=2, ensure_ascii=False), encoding='utf-8')
    print(json.dumps({'summary_path': str(summary_path), **summary}, indent=2, ensure_ascii=False))
    return 0 if summary['verdict'] == 'GO' else 2


if __name__ == '__main__':
    raise SystemExit(main())
