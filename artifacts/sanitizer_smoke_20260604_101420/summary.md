# Sanitizer smoke summary

- Run timestamp UTC: 2026-06-04T10:19:48.033532+00:00
- Existing production smoke reusable: no; it depends on Supabase/storage/prod HTTP and environment variables.
- Source pipeline: local fixture PDF -> extract_pdf_text -> sanitize_source_text -> build_whub_json with stubbed HermesRunner -> enforce/sanitize/assert JSON -> render_pdf -> run_qa.
- Generated PDF: /root/whub-cv-factory/artifacts/sanitizer_smoke_20260604_101420/output.pdf

## Sanitization report counts
- raw_chars: 1486
- sanitized_chars: 1036
- removed_email_count: 1
- removed_phone_count: 1
- removed_url_count: 1
- removed_linkedin_count: 1
- removed_github_profile_count: 1
- removed_address_line_count: 2
- removed_contact_label_line_count: 1
- removed_hellowork_line_count: 7
- removed_empty_or_boilerplate_line_count: 5
- warnings: ['hellowork_boilerplate_removed']

## Structuring result
- name: JEAN
- title: Chef de projet Data et Cloud
- formations: 2
- skills: 2
- experiences: 1
- first_name_only_enforced: True
- contact_json_assertion: passed

## QA report summary
- contact_hits: []
- layout_issues: []
- has_logo: True
- has_watermark: True
- pages: 1
- passed: True
- draft: False
- failed: False
- status: passed

## Safe event confirmation
- A source_sanitized event would be safe: only counters and generic warnings are written; no removed raw email, phone, URL, address, or profile values are stored.
- Artifact contact scan: passed for text artifacts and rendered PDF QA; raw fixture PDF was temporary outside this artifact directory and deleted after extraction.
