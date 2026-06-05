# HODARD smoke summary — incident 82c6a49f

- Run timestamp UTC: 2026-06-04T13:01:44.262553+00:00
- Source: `/tmp/hodard_source.pdf` (real incident source)
- Pipeline: extract_pdf_text → sanitize_source_text → build_whub_json (stubbed HermesRunner) → enforce_client_first_name → render_pdf → run_qa
- Generated PDF: /root/whub-cv-factory/artifacts/smoke_hodard_20260604_124550/output.pdf
- Smoke script: /root/whub-cv-factory/artifacts/smoke_hodard_20260604_124550/smoke.py

## Inference
- Inferred first name: `FLORIAN`
- Inferred surname (forbidden): `['HODARD']`
- `infer_forbidden_candidate_identity_terms(text, "")` returned: ['HODARD']

## Sanitization report counts
- raw_chars: 4405
- sanitized_chars: 4153
- removed_email_count: 1
- removed_phone_count: 1
- removed_url_count: 4
- removed_linkedin_count: 0
- removed_github_profile_count: 0
- removed_address_line_count: 0
- removed_contact_label_line_count: 0
- removed_hellowork_line_count: 2
- removed_empty_or_boilerplate_line_count: 2
- warnings: ['hellowork_boilerplate_removed']

## Structuring result
- name: FLORIAN
- title: Ingénieur DevOps / Full-Stack
- formations: 1
- skills: 10
- experiences: 2
- first_name_only_enforced: True
- contact_json_assertion: passed

## QA report summary
- contact_hits: []
- layout_issues: []
- content_integrity_issues: 2 items (expected — synthetic structured data, not real LLM output)
- has_logo: True
- has_watermark: True
- pages: 2
- passed: False
- identity_checks_pass: True
- status: identity_only
