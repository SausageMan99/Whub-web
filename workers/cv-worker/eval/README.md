# W hub CV Factory — Evaluation Corpus

This folder defines anonymized benchmark cases for W hub CV Factory.
The runner is `run_eval.py` and is intentionally pure-Python, dependency-free
and read-only: it never calls the model, never touches the database, never
writes to Supabase storage.

## Rules

- **Do not commit raw candidate CVs** unless they are anonymized and approved
  by Clément. The corpus is reviewed case-by-case.
- **Do not commit emails, phones, LinkedIn, addresses, full names, private
  URLs, or source PDFs containing contact information.** Synthetic fixtures
  that reproduce a bug class are preferred over real data.
- **Every production incident fixed in worker / QA / layout should add one
  case or one assertion here.** The corpus is the regression test for the
  auto-evaluation loop.
- Keep fixtures small (< 8 KB) and deterministic.

## Case schema

```json
{
  "id": "stable_slug",
  "profile": "normal|senior_long|ats|scanned|two_column|graphic|risky",
  "input_kind": "text|pdf_path",
  "input_path": "relative fixture path",
  "assertions": {
    "expected_status": "ready|draft_ready|needs_human_review|qa_failed|failed",
    "required_terms": ["React", "AWS"],
    "forbidden_patterns": ["@", "linkedin\\.com"],
    "max_pages": 4,
    "disallowed_qa_codes": ["contact_leak", "candidate_identity_term_exposed"]
  }
}
```

`expected_status` is optional. When set, the runner checks the status field
in the result JSON. `required_terms` and `forbidden_patterns` are checked
against the `pdf_text` field of the result. `max_pages` is checked against
`qa_report.pages`. `disallowed_qa_codes` is checked against
`qa_report.layout_issues[*].code`.

## Running

```bash
cd workers/cv-worker
uv run python eval/run_eval.py --case eval/cases/example_case.json --result path/to/result.json
```

The runner exits with status 0 on PASS and non-zero on FAIL. CI usage is
described in `docs/verify_quality_loop.sh`.
