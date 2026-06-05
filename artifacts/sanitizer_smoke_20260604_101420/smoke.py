#!/usr/bin/env python3
from __future__ import annotations

import json
import re
import sys
import tempfile
from dataclasses import asdict
from pathlib import Path
from datetime import datetime, timezone

from reportlab.lib.pagesizes import A4
from reportlab.pdfgen import canvas

REPO = Path(__file__).resolve().parents[2]
WORKER = REPO / "workers" / "cv-worker"
sys.path.insert(0, str(WORKER))

from src.extraction import extract_pdf_text
from src.source_sanitizer import sanitize_source_text
from src.structuring import (
    assert_no_contact_in_json,
    build_whub_json,
    enforce_client_first_name,
    sanitize_contact_in_json,
)
from src.rendering import render_pdf
from src.qa import QAError, run_qa

OUTDIR = Path(__file__).resolve().parent
CONTACT_PATTERNS = {
    "email": re.compile(r"[a-z0-9._%+-]+@[a-z0-9.-]+\.[a-z]{2,}", re.I),
    "phone_fr": re.compile(r"(?<!\d)(?:\+33\s?|0)[67](?:[\s.\-]?\d{2}){4}(?!\d)", re.I),
    "linkedin_profile": re.compile(r"(?:linkedin\.com/in/|lnkd\.in/)", re.I),
    "github_profile": re.compile(r"github\.com/[A-Za-z0-9-]+", re.I),
    "url": re.compile(r"https?://|www\.", re.I),
}


def make_fixture_text() -> str:
    # Build contact surfaces from fragments so this temporary validation script
    # does not itself store full raw contact values as contiguous artifact text.
    candidate_first = "Jean"
    candidate_last = "Du" + "pont"
    email = "jean" + ".du" + "pont" + "@" + "example" + ".com"
    phone = "06" + " 12" + " 34" + " 56" + " 78"
    scheme = "h" + "ttps" + "://"
    www = "w" + "ww" + "."
    linkedin = scheme + www + "linked" + "in" + ".com/in/" + "jean-" + "du" + "pont-data"
    github = scheme + "git" + "hub" + ".com/" + "jdu" + "pont-data"
    portfolio = scheme + "portfolio" + ".dev/" + "jean"
    address_1 = "42 " + ("r" + "ue") + " des " + "Lilas"
    address_2 = "750" + "11 " + "Paris"
    return f"""
CV téléchargé depuis Hellowork
Profil consulté par un recruteur Hellowork
{candidate_first} {candidate_last}
Chef de projet Data et Cloud
Coordonnées
Email : {email}
Téléphone : {phone}
LinkedIn : {linkedin}
GitHub : {github}
Portfolio : {portfolio}
Adresse : {address_1}
{address_2}
Disponibilité : immédiate
TJM : information ATS

Profil
Chef de projet Data et Cloud avec 8 ans d'expérience dans la transformation numérique.
Pilotage de programmes data, migration cloud et coordination d'équipes agiles.

Compétences
Gestion de projet : Scrum, Kanban, planning, budget, risques.
Data & Cloud : AWS, Azure, Snowflake, Power BI, Python, SQL.
DevOps : GitHub Actions, Docker, Kubernetes, Jenkins.
Marketing digital : campagnes LinkedIn Ads et emailing B2B.
Projets : plateforme Th@Bot et API REST Node.js.

Expériences professionnelles
Janvier 2022 - Mars 2026
Chef de projet Data | GROUPE ATLAS | Paris (75)
Pilotage du programme de migration cloud AWS pour les applications décisionnelles.
Coordination de 12 contributeurs métier, data engineering et sécurité.
Mise en place de tableaux de bord Power BI pour le suivi des indicateurs opérationnels.
Animation des comités hebdomadaires et reporting exécutif.

Formations
2016 - Master Management des Systèmes d'Information - IAE Paris
2014 - Licence Informatique - Université Paris Cité

Mettre à jour mon CV
Voir le profil Hellowork
Candidature transmise via ATS
""".strip()


def write_fixture_pdf(text: str, path: Path) -> None:
    c = canvas.Canvas(str(path), pagesize=A4)
    width, height = A4
    y = height - 48
    c.setFont("Helvetica", 9)
    for raw_line in text.splitlines():
        line = raw_line[:110]
        if y < 48:
            c.showPage()
            c.setFont("Helvetica", 9)
            y = height - 48
        c.drawString(48, y, line)
        y -= 12
    c.save()


def stub_structured_json() -> dict:
    candidate_first = "Jean"
    candidate_last = "Du" + "pont"
    return {
        "name": f"{candidate_first} {candidate_last}",
        "title": "Chef de projet Data et Cloud",
        "description": "Chef de projet Data et Cloud avec 8 ans d'expérience dans la transformation numérique.",
        "formations": [
            {"date": "2016", "degree": "Master Management des Systèmes d'Information", "school": "IAE Paris"},
            {"date": "2014", "degree": "Licence Informatique", "school": "Université Paris Cité"},
        ],
        "skills": [
            {"category": "Gestion de projet", "items": ["Scrum", "Kanban", "planning", "budget", "risques"]},
            {"category": "Data & Cloud", "items": ["AWS", "Azure", "Snowflake", "Power BI", "Python", "SQL"]},
            {"category": "DevOps", "items": ["GitHub Actions", "Docker", "Kubernetes", "Jenkins"]},
            {"category": "Marketing digital", "items": ["campagnes LinkedIn Ads", "emailing B2B"]},
            {"category": "Projets", "items": ["plateforme Th@Bot", "API REST Node.js"]},
        ],
        "experiences": [
            {
                "date": "Janvier 2022 - Mars 2026",
                "role": "Chef de projet Data | GROUPE ATLAS | Paris (75)",
                "company_highlight": "GROUPE ATLAS",
                "sections": [
                    {"heading": "Missions", "content": [
                        "Pilotage du programme de migration cloud AWS pour les applications décisionnelles.",
                        "Coordination de 12 contributeurs métier, data engineering et sécurité.",
                        "Mise en place de tableaux de bord Power BI pour le suivi des indicateurs opérationnels.",
                        "Animation des comités hebdomadaires et reporting exécutif.",
                    ]},
                ],
            },
        ],
    }


def make_runner(expected_sanitized_text: str):
    def runner(prompt: str, timeout: int) -> tuple[int, str, str]:
        # The model boundary must receive sanitized source only.
        forbidden_in_prompt = [name for name, pat in CONTACT_PATTERNS.items() if pat.search(prompt)]
        if forbidden_in_prompt:
            return 2, "", "prompt contained contact surfaces: " + ",".join(forbidden_in_prompt)
        if "CV téléchargé depuis Hellowork" in prompt or "Profil consulté" in prompt:
            return 2, "", "prompt contained Hellowork boilerplate"
        for business_phrase in [
            "GROUPE ATLAS",
            "GitHub Actions",
            "LinkedIn Ads",
            "Th@Bot",
            "API REST Node.js",
            "Power BI",
        ]:
            if business_phrase not in prompt:
                return 2, "", "prompt lost business phrase"
        return 0, json.dumps(stub_structured_json(), ensure_ascii=False), ""
    return runner


def assert_no_contact_surfaces(text: str, label: str) -> None:
    hits = [name for name, pattern in CONTACT_PATTERNS.items() if pattern.search(text or "")]
    if hits:
        raise AssertionError(f"{label} still contains contact surfaces: {hits}")


def write_json(path: Path, data: object) -> None:
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")


def main() -> None:
    fixture_text = make_fixture_text()
    OUTDIR.mkdir(parents=True, exist_ok=True)

    with tempfile.TemporaryDirectory(prefix="whub_sanitizer_smoke_") as tmp:
        source_pdf = Path(tmp) / "source_fixture.pdf"
        write_fixture_pdf(fixture_text, source_pdf)

        extracted_text = extract_pdf_text(source_pdf)
        assert len(extracted_text.strip()) >= 400

    sanitized = sanitize_source_text(extracted_text, "Jean")
    assert_no_contact_surfaces(sanitized.text, "sanitized source")
    for removed_noise in ["Hellowork", "Profil consulté", "Mettre à jour mon CV", "Candidature transmise"]:
        if removed_noise.lower() in sanitized.text.lower():
            raise AssertionError(f"sanitized source retained boilerplate: {removed_noise}")
    for business_phrase in ["GROUPE ATLAS", "GitHub Actions", "LinkedIn Ads", "Th@Bot", "API REST Node.js"]:
        if business_phrase not in sanitized.text:
            raise AssertionError(f"sanitizer removed business phrase: {business_phrase}")

    structured = build_whub_json(
        sanitized.text,
        "CV standard W hub fidèle. Conserver les faits source sans coordonnées candidat.",
        [],
        "Jean",
        hermes_runner=make_runner(sanitized.text),
        fallback_runner=None,
    )
    enforce_client_first_name(structured, "Jean")
    structured = sanitize_contact_in_json(structured)
    assert_no_contact_in_json(structured)
    if structured.get("name") != "JEAN":
        raise AssertionError(f"expected first-name-only JEAN, got {structured.get('name')!r}")

    # Renderer JSON is the structured JSON after first-name/contact enforcement.
    renderer_json = dict(structured)
    assert_no_contact_in_json(renderer_json)
    write_json(OUTDIR / "structured_renderer_input.json", renderer_json)

    pdf_path = render_pdf(renderer_json, OUTDIR, output_name="output.pdf")
    if not pdf_path.exists() or pdf_path.stat().st_size <= 0:
        raise AssertionError("rendered PDF missing or empty")

    try:
        forbidden_surname = "Du" + "pont"
        qa_report = run_qa(pdf_path, forbidden_names=[forbidden_surname], source_text=sanitized.text, structured_data=renderer_json)
    except QAError as exc:
        write_json(OUTDIR / "qa_report_failed.json", exc.report)
        raise

    if qa_report.get("contact_hits") != []:
        raise AssertionError(f"QA contact_hits not empty: {qa_report.get('contact_hits')}")
    if qa_report.get("has_logo") is not True or qa_report.get("has_watermark") is not True:
        raise AssertionError("QA did not detect required logo/watermark")

    write_json(OUTDIR / "sanitization_report.json", asdict(sanitized.report))
    write_json(OUTDIR / "qa_report.json", qa_report)

    artifact_text_paths = [
        OUTDIR / "structured_renderer_input.json",
        OUTDIR / "sanitization_report.json",
        OUTDIR / "qa_report.json",
    ]
    for path in artifact_text_paths:
        assert_no_contact_surfaces(path.read_text(encoding="utf-8"), str(path))

    status = "passed" if qa_report.get("passed") else "draft" if not qa_report.get("contact_hits") else "failed"
    report = sanitized.report
    summary = f"""# Sanitizer smoke summary

- Run timestamp UTC: {datetime.now(timezone.utc).isoformat()}
- Existing production smoke reusable: no; it depends on Supabase/storage/prod HTTP and environment variables.
- Source pipeline: local fixture PDF -> extract_pdf_text -> sanitize_source_text -> build_whub_json with stubbed HermesRunner -> enforce/sanitize/assert JSON -> render_pdf -> run_qa.
- Generated PDF: {pdf_path}

## Sanitization report counts
- raw_chars: {report.raw_chars}
- sanitized_chars: {report.sanitized_chars}
- removed_email_count: {report.removed_email_count}
- removed_phone_count: {report.removed_phone_count}
- removed_url_count: {report.removed_url_count}
- removed_linkedin_count: {report.removed_linkedin_count}
- removed_github_profile_count: {report.removed_github_profile_count}
- removed_address_line_count: {report.removed_address_line_count}
- removed_contact_label_line_count: {report.removed_contact_label_line_count}
- removed_hellowork_line_count: {report.removed_hellowork_line_count}
- removed_empty_or_boilerplate_line_count: {report.removed_empty_or_boilerplate_line_count}
- warnings: {list(report.warnings)}

## Structuring result
- name: {renderer_json.get('name')}
- title: {renderer_json.get('title')}
- formations: {len(renderer_json.get('formations', []))}
- skills: {len(renderer_json.get('skills', []))}
- experiences: {len(renderer_json.get('experiences', []))}
- first_name_only_enforced: {renderer_json.get('name') == 'JEAN'}
- contact_json_assertion: passed

## QA report summary
- contact_hits: {qa_report.get('contact_hits')}
- layout_issues: {qa_report.get('layout_issues')}
- has_logo: {qa_report.get('has_logo')}
- has_watermark: {qa_report.get('has_watermark')}
- pages: {qa_report.get('pages')}
- passed: {qa_report.get('passed')}
- draft: {status == 'draft'}
- failed: {status == 'failed'}
- status: {status}

## Safe event confirmation
- A source_sanitized event would be safe: only counters and generic warnings are written; no removed raw email, phone, URL, address, or profile values are stored.
- Artifact contact scan: passed for text artifacts and rendered PDF QA; raw fixture PDF was temporary outside this artifact directory and deleted after extraction.
"""
    (OUTDIR / "summary.md").write_text(summary, encoding="utf-8")
    assert_no_contact_surfaces(summary, "summary")

    print(json.dumps({
        "artifact_dir": str(OUTDIR),
        "pdf": str(pdf_path),
        "summary": str(OUTDIR / "summary.md"),
        "sanitization_counts": asdict(report),
        "qa": {
            "contact_hits": qa_report.get("contact_hits"),
            "layout_issues": qa_report.get("layout_issues"),
            "has_logo": qa_report.get("has_logo"),
            "has_watermark": qa_report.get("has_watermark"),
            "pages": qa_report.get("pages"),
            "passed": qa_report.get("passed"),
            "draft": status == "draft",
            "failed": status == "failed",
        },
        "source_sanitized_event_safe": True,
    }, indent=2, ensure_ascii=False))


if __name__ == "__main__":
    main()
