# Sanitize-before-structuring + QA-after-structuring Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task. Do not deploy or restart the worker until all tests, local smoke, and independent review are green, then require Clément's explicit release approval.

**Goal:** Introduce a safe pre-structuring sanitization boundary so the model receives a cleaned CV text instead of raw contact-heavy source text, while preserving source fidelity and keeping strict post-structuring/post-render QA before any CV can be delivered to W hub users.

**Architecture:** Add a deterministic source-text sanitizer between `extract_pdf_text()` and `build_whub_json()`. Keep the raw PDF/text available only for internal audit and forbidden-identity inference, pass `sanitized_text` to the structuring model and source-fidelity checks, then run strict JSON QA and PDF QA after structuring/rendering. Persist only safe sanitization counters/warnings, never raw removed contact values.

**Tech Stack:** Python worker in `/root/whub-cv-factory/workers/cv-worker`, PyMuPDF extraction/QA, existing `pytest` suite, Supabase `cv_events`/`cv_requests`, existing renderer/layout variant loop.

---

## Current context

The current worker flow is in `workers/cv-worker/src/main.py`:

```text
download_source → extract_pdf_text → build_whub_json(raw text) → assert_no_contact_in_json → render/layout variants → run_qa(pdf, source_text=raw text) → save_version
```

Key existing files:

- `workers/cv-worker/src/extraction.py`: only extracts raw PDF text today.
- `workers/cv-worker/src/structuring.py`: contains JSON contact sanitization (`sanitize_contact_in_json`) and `assert_no_contact_in_json`, but this happens after the model has already seen the extracted text.
- `workers/cv-worker/src/qa.py`: strict PDF QA already detects emails, phones, URLs, LinkedIn URLs and forbidden names after render.
- `workers/cv-worker/src/main.py`: currently passes raw extracted text into `build_whub_json()` and into `run_bounded_layout_variant_loop(... source_text=text)`.
- Existing tests already cover contact QA, draft blockers, source coverage, layout variants, structuring and safe error taxonomy.

Important existing behavior to preserve:

- First-name-only display.
- No candidate phone/email/LinkedIn/address/portfolio in final PDF.
- Source fidelity: no missing business sections, no rewriting unless explicitly requested.
- No raw sensitive data in `last_error`, events, QA reports, logs or stored JSON.
- Hard blockers remain hard: contact leak, identity leak, source fidelity failure, renderer assets, text overflow.
- Soft layout issues can still produce `draft_ready` only when there is no contact/fidelity/security failure.

---

## Proposed approach

Add a new sanitizer module rather than burying regexes inside `structuring.py`. The sanitizer should be deterministic, audited by tests, and return a safe report.

New conceptual boundary:

```text
PDF brut/source.pdf
  ↓
extract_pdf_text() → raw_text
  ↓
sanitize_source_text(raw_text, candidate_first_name, filename/source metadata)
  ↓
sanitized_text + safe sanitization_report
  ↓
build_whub_json(sanitized_text, instructions, comments, candidate_first_name)
  ↓
sanitize_contact_in_json(structured)
  ↓
assert_no_contact_in_json(structured) [strict, context-aware]
  ↓
validate_source_fidelity(sanitized_text, structured)
  ↓
render/layout variants
  ↓
run_qa(pdf, forbidden_names=derived from raw/sanitized text, source_text=sanitized_text, structured_data=structured)
  ↓
save_version only if QA passed/draft-safe
```

Raw text remains available in memory for forbidden-name inference and audit-only diagnostics, but the model and source coverage checks use sanitized text.

---

## Non-negotiable acceptance criteria

1. The model never receives obvious contact data when deterministic sanitization can remove it first.
2. The sanitizer never stores raw removed emails, phone numbers, addresses or URLs in events/errors/reports.
3. Hellowork boilerplate is removed without deleting real CV business content.
4. `GitHub Actions`, `LinkedIn Ads`, `Th@Bot`, `emailing`, `Node.js`, `API REST`, company/client domains inside names, and project names with symbols do not trigger false contact blocks by themselves.
5. Real emails, French mobile numbers, full LinkedIn/GitHub/profile URLs, portfolio URLs and candidate addresses are removed before structuring and blocked if they reappear after structuring/rendering.
6. Source-fidelity QA compares against sanitized business content, not against removed contact/boilerplate lines.
7. Final PDF QA remains strict and is run on the actual rendered PDF selected by the layout variant loop.
8. `qa_failed`/`failed` events remain safe public messages with safe categories only.
9. Production release requires tests, py_compile, renderer/preflight smoke, one real CV smoke, worker restart verification, and explicit Clément approval.

---

## Files likely to change

Create:

- `workers/cv-worker/src/source_sanitizer.py`
- `workers/cv-worker/tests/test_source_sanitizer.py`

Modify:

- `workers/cv-worker/src/main.py`
- `workers/cv-worker/src/structuring.py`
- `workers/cv-worker/src/qa.py`
- `workers/cv-worker/tests/test_structuring.py`
- `workers/cv-worker/tests/test_qa.py`
- `workers/cv-worker/tests/test_draft_ready.py`
- `workers/cv-worker/tests/test_main_error_taxonomy.py`
- Possibly `workers/cv-worker/src/events.py` only if event payload shaping needs a central safety helper.
- Possibly `workers/cv-worker/README.md` to document the new pipeline.

Do not change during this plan unless implementation proves necessary:

- Supabase schema.
- Renderer visual layout.
- Portal UI.
- Auth/RLS.
- Vercel web app.

---

## Data contract for the sanitizer

Implement a small dataclass or typed dict:

```python
@dataclass(frozen=True)
class SanitizationReport:
    raw_chars: int
    sanitized_chars: int
    removed_email_count: int = 0
    removed_phone_count: int = 0
    removed_url_count: int = 0
    removed_linkedin_count: int = 0
    removed_github_profile_count: int = 0
    removed_address_line_count: int = 0
    removed_contact_label_line_count: int = 0
    removed_hellowork_line_count: int = 0
    removed_empty_or_boilerplate_line_count: int = 0
    warnings: tuple[str, ...] = ()
```

Rules:

- The report must contain counts/categories only.
- No raw candidate email, phone, URL, address, surname, filename or source line in the report.
- If an ambiguous line is preserved, report a generic warning such as `ambiguous_contact_label_preserved` without the line content.
- If sanitization removes too much text, report `sanitized_text_shrunk_unusually` and let the worker fail safely before model structuring.

---

## Detailed implementation plan

### Task 1: Add source sanitizer tests first

**Objective:** Define the safe behavior before touching the worker pipeline.

**Files:**

- Create: `workers/cv-worker/tests/test_source_sanitizer.py`
- Create later: `workers/cv-worker/src/source_sanitizer.py`

**Test cases to add:**

1. Removes direct email without storing raw value in report.
2. Removes French mobile formats: `06 12 34 56 78`, `07.12.34.56.78`, `+33 6 12 34 56 78`.
3. Removes LinkedIn profile URLs and `lnkd.in` URLs.
4. Removes GitHub profile URLs such as `github.com/jdupont`, but preserves `GitHub Actions`.
5. Removes personal/portfolio URLs: `https://portfolio.dev`, `www.jean-dupont.fr`.
6. Preserves technical terms: `Th@Bot`, `emailing`, `LinkedIn Ads`, `GitHub Actions`, `Node.js`, `.NET`, `API REST`.
7. Removes Hellowork boilerplate lines without removing experience lines.
8. Removes contact label-only lines: `Coordonnées`, `Contact`, `Téléphone`, `Email`, `LinkedIn` when isolated.
9. Removes likely address lines only when context indicates candidate contact/header, not experience location facts.
10. Returns a report with counts and no raw sensitive substring.
11. Raises/fails safely if sanitized text becomes too short or loses a high percentage of content.

**Example test skeleton:**

```python
from src.source_sanitizer import sanitize_source_text


def test_sanitizer_removes_email_and_phone_without_leaking_report():
    raw = """
Jean Dupont
jean.dupont@example.com
06 12 34 56 78
Architecte Solution AWS
Expérience chez EDF : migration Kubernetes
"""

    result = sanitize_source_text(raw, candidate_first_name="Jean")

    assert "jean.dupont@example.com" not in result.text
    assert "06 12 34 56 78" not in result.text
    assert "Architecte Solution AWS" in result.text
    assert "migration Kubernetes" in result.text
    assert result.report.removed_email_count == 1
    assert result.report.removed_phone_count == 1
    assert "jean.dupont" not in repr(result.report).lower()
    assert "0612345678" not in repr(result.report).replace(" ", "")
```

**Command:**

```bash
cd /root/whub-cv-factory/workers/cv-worker
pytest tests/test_source_sanitizer.py -v
```

**Expected before implementation:** FAIL because `src.source_sanitizer` does not exist.

---

### Task 2: Implement `source_sanitizer.py`

**Objective:** Add deterministic pre-model sanitization with safe reporting.

**Files:**

- Create: `workers/cv-worker/src/source_sanitizer.py`

**Implementation details:**

Define:

```python
@dataclass(frozen=True)
class SourceSanitizationResult:
    text: str
    report: SanitizationReport
```

Main function:

```python
def sanitize_source_text(
    raw_text: str,
    candidate_first_name: str | None = None,
    *,
    min_chars: int = 400,
) -> SourceSanitizationResult:
    ...
```

Sanitization strategy:

- Normalize line endings.
- Process line-by-line first for boilerplate/contact-label/address lines.
- Then apply inline substitutions for emails, phones and URLs inside otherwise useful lines.
- Collapse repeated blank lines.
- Preserve original order of business content.
- Never deduplicate non-empty business lines globally, because repeated stacks/dates can be meaningful.

Regex groups:

- Email: real email pattern only, not bare `@`.
- Phone: French mobile and `+33` mobile/portable formats.
- LinkedIn URL/profile: `linkedin.com/in/...`, `fr.linkedin.com/in/...`, `lnkd.in/...`.
- GitHub profile URL: `github.com/<handle>` only when URL/profile-like; preserve `GitHub Actions` and plain `GitHub`.
- URL: `https?://...`, `www....`, domains with path when likely personal/contact.
- Contact labels: isolated labels or header labels followed by known contact value.
- Hellowork boilerplate: lines containing `hellowork`, `cv téléchargé`, `profil consulté`, `candidature`, `mettre à jour mon cv`, `voir le profil`, `téléchargé depuis`, and similar export noise.
- Address: conservative. Only remove when near header/contact section or matching strong French address pattern with postal code + city. Do not remove experience location facts like `Paris`, `La Défense`, `Nanterre`, `Remote`, `Lyon` alone.

Critical guard:

```python
if len(sanitized.strip()) < min_chars:
    raise SourceSanitizationError("Texte source trop court après sanitization")
```

Add shrink warning if sanitized length drops below e.g. 55% of raw length, but do not fail automatically unless below `min_chars` or business-section markers are gone.

**Command:**

```bash
cd /root/whub-cv-factory/workers/cv-worker
pytest tests/test_source_sanitizer.py -v
```

**Expected after implementation:** PASS.

---

### Task 3: Integrate sanitizer into `process_job()` before structuring

**Objective:** Ensure the model receives `sanitized_text`, not raw extracted text.

**Files:**

- Modify: `workers/cv-worker/src/main.py`
- Modify: `workers/cv-worker/tests/test_draft_ready.py`
- Possibly modify/add: `workers/cv-worker/tests/test_main_error_taxonomy.py`

**Current code:**

```python
text = extract_pdf_text(source)
timings["extract_text"] = perf_counter() - stage_start
emit_event(request_id, "extraction_done", {"chars": len(text)})
...
structured = build_whub_json(text, job.get("instructions") or "", comments_for_prompt, job.get("candidate_first_name"))
...
forbidden_names = forbidden_candidate_name_parts(job.get("candidate_first_name"), text)
variant_selection = run_bounded_layout_variant_loop(... source_text=text)
```

**Target behavior:**

```python
raw_text = extract_pdf_text(source)
...
sanitized = sanitize_source_text(raw_text, job.get("candidate_first_name"))
sanitized_text = sanitized.text
emit_event(request_id, "source_sanitized", safe_report_payload(sanitized.report))
...
structured = build_whub_json(sanitized_text, instructions, comments_for_prompt, candidate_first_name)
...
forbidden_names = forbidden_candidate_name_parts(candidate_first_name, raw_text)
variant_selection = run_bounded_layout_variant_loop(... source_text=sanitized_text)
```

Important distinction:

- Use `raw_text` for `forbidden_candidate_name_parts()` because the source header may contain surname/full identity that should never appear in the final PDF.
- Use `sanitized_text` for `build_whub_json()` and `run_qa(... source_text=...)` because source coverage must not demand removed contact/Hellowork lines.
- Use `sanitized_text` for any model prompt.
- Event payload must contain only counts and warning codes.

**Tests:**

Add/update a process-job test that monkeypatches:

- `extract_pdf_text` returns text containing `jean@example.com`, `linkedin.com/in/jean`, Hellowork noise and business content.
- `build_whub_json` captures the text argument.
- Assert captured text does not contain email/LinkedIn/Hellowork.
- Assert captured text still contains skills/experiences.
- Assert `run_bounded_layout_variant_loop` receives `source_text=sanitized_text`.
- Assert `forbidden_candidate_name_parts` still receives raw text or still blocks surname inferred from raw text.

**Command:**

```bash
cd /root/whub-cv-factory/workers/cv-worker
pytest tests/test_draft_ready.py tests/test_main_error_taxonomy.py -v
```

**Expected:** PASS.

---

### Task 4: Make JSON contact QA context-aware and strict on real leaks

**Objective:** Avoid false positives from generic tokens while keeping real contact surfaces blocked.

**Files:**

- Modify: `workers/cv-worker/src/structuring.py`
- Modify: `workers/cv-worker/tests/test_structuring.py`

**Current risk:**

`CONTACT_PATTERNS` currently includes broad patterns like `r"linkedin"`, `r"github\.com"`, `r"https?://"`, `r"\bwww\."`, `r"\+33"`. This is better than blocking bare `@`, but `linkedin` alone can still create false positives for legitimate content such as `LinkedIn Ads`.

**Target behavior:**

- `assert_no_contact_in_json()` should report stable hit categories, not raw regex strings.
- Block:
  - real emails;
  - real French phone numbers;
  - LinkedIn profile URLs and `lnkd.in`;
  - GitHub profile URLs;
  - generic profile/portfolio URLs;
  - obvious address/contact fields.
- Do not block:
  - `LinkedIn Ads`;
  - `GitHub Actions`;
  - `Th@Bot`;
  - `emailing`;
  - `contact client` in a mission sentence if no direct coordinate follows.

Preferred implementation:

```python
CONTACT_DETECTORS = {
    "email": EMAIL_CONTACT_RE,
    "phone_fr": PHONE_CONTACT_RE,
    "linkedin_profile": LINKEDIN_PROFILE_CONTACT_RE,
    "github_profile": GITHUB_PROFILE_CONTACT_RE,
    "url": URL_CONTACT_RE,
}
```

`assert_no_contact_in_json(data)` should raise:

```python
StructuringError("Coordonnées détectées dans JSON renderer: ['email', 'phone_fr']")
```

No raw sensitive values in error.

**Tests:**

- `assert_no_contact_in_json` raises for `jean@example.com`.
- Raises for `0612345678`.
- Raises for `linkedin.com/in/jean-dupont`.
- Raises for `https://portfolio-jean.fr`.
- Does not raise for `Th@Bot`.
- Does not raise for `LinkedIn Ads`.
- Does not raise for `GitHub Actions`.
- Does not include raw email/phone in exception string.

**Command:**

```bash
cd /root/whub-cv-factory/workers/cv-worker
pytest tests/test_structuring.py -k "contact or sanitize or github or linkedin" -v
```

**Expected:** PASS.

---

### Task 5: Keep JSON auto-sanitization but treat residual real leaks as hard blockers at the worker boundary

**Objective:** Separate safe autoclean from final blocking.

**Files:**

- Modify: `workers/cv-worker/src/structuring.py`
- Modify: `workers/cv-worker/src/main.py`
- Modify/add tests in `workers/cv-worker/tests/test_structuring.py` and `workers/cv-worker/tests/test_draft_ready.py`

**Current behavior:**

Inside `build_whub_json`, the code sanitizes structured JSON, calls `assert_no_contact_in_json`, catches `StructuringError`, logs a warning and continues.

That is acceptable only if the residual hit is known false-positive. After making contact detection contextual, residual real leaks should not be silently tolerated.

**Target behavior:**

- `sanitize_contact_in_json(data)` remains automatic.
- `assert_no_contact_in_json(data)` becomes reliable enough to hard-block real residual leaks.
- Remove or narrow this code path:

```python
try:
    assert_no_contact_in_json(data)
except StructuringError as contact_exc:
    log.warning("contact surfaces remained after sanitization; continuing: %s", contact_exc)
```

Replace with either:

```python
assert_no_contact_in_json(data)
```

or, if a warning path is still needed, only for explicitly classified non-contact-safe warnings that do not include real contact detector categories.

**Critical point:** do not reintroduce raw contact values in logs.

**Tests:**

- A model output containing email after `sanitize_contact_in_json` should be cleaned and pass if the cleaned sentence remains useful.
- A model output containing a malformed but still real contact surface that cannot be cleaned should fail with `contact_leak`.
- A model output containing `LinkedIn Ads` should pass.
- A model output containing `Th@Bot` should pass.

**Command:**

```bash
cd /root/whub-cv-factory/workers/cv-worker
pytest tests/test_structuring.py tests/test_draft_ready.py -v
```

**Expected:** PASS.

---

### Task 6: Align PDF QA contact detection with the new contact semantics

**Objective:** Keep final PDF QA strict for real leaks but avoid generic false positives.

**Files:**

- Modify: `workers/cv-worker/src/qa.py`
- Modify: `workers/cv-worker/tests/test_qa.py`

**Current PDF QA patterns:**

```python
CONTACT_PATTERNS = {
    "email": ...,
    "linkedin": r"(?:https?://)?(?:www\.)?(?:[a-z]{2}\.)?linkedin\.com/\S+|lnkd\.in/\S+",
    "url": ... github.com/\S+ ...,
    "phone_fr": ...,
}
```

This is mostly correct. Still add explicit tests to lock semantics:

- PDF with `LinkedIn Ads` should not fail.
- PDF with `GitHub Actions` should not fail.
- PDF with `linkedin.com/in/jean` should fail.
- PDF with `github.com/jean` should fail.
- PDF with `Th@Bot` should not fail.
- PDF with `a@b.com` should fail.

**Command:**

```bash
cd /root/whub-cv-factory/workers/cv-worker
pytest tests/test_qa.py -k "contact or linkedin or github" -v
```

**Expected:** PASS.

---

### Task 7: Add safe sanitization event and error taxonomy coverage

**Objective:** Give ops enough visibility without leaking candidate data.

**Files:**

- Modify: `workers/cv-worker/src/main.py`
- Modify: `workers/cv-worker/tests/test_main_error_taxonomy.py`
- Possibly modify: `workers/cv-worker/src/structuring.py` if `classify_structuring_error` needs a new category.

**Event to emit:**

After sanitization:

```python
emit_event(request_id, "source_sanitized", {
    "raw_chars": report.raw_chars,
    "sanitized_chars": report.sanitized_chars,
    "removed_email_count": report.removed_email_count,
    "removed_phone_count": report.removed_phone_count,
    "removed_url_count": report.removed_url_count,
    "removed_linkedin_count": report.removed_linkedin_count,
    "removed_github_profile_count": report.removed_github_profile_count,
    "removed_address_line_count": report.removed_address_line_count,
    "removed_hellowork_line_count": report.removed_hellowork_line_count,
    "warnings": list(report.warnings),
})
```

Never include:

- raw source lines;
- removed email;
- removed phone;
- removed URL;
- removed address;
- candidate full name;
- filename if it may contain surname.

Add failure classification for sanitizer errors:

- `source_sanitization` or map to safe `contact_leak`/`structuring_invalid_json` depending on existing taxonomy preference.
- Public message should be generic, e.g. `Nettoyage de la source CV impossible sans risque de perte de contenu.`

**Tests:**

- Event payload contains counts.
- Event payload does not contain raw email/phone/url.
- Sanitizer failure sets safe `last_error` and safe `error_category`.

**Command:**

```bash
cd /root/whub-cv-factory/workers/cv-worker
pytest tests/test_main_error_taxonomy.py tests/test_draft_ready.py -v
```

**Expected:** PASS.

---

### Task 8: Ensure source-fidelity QA uses sanitized business source, not raw contact source

**Objective:** Prevent QA from failing because contact/Hellowork lines were intentionally removed.

**Files:**

- Modify: `workers/cv-worker/src/main.py`
- Possibly modify: `workers/cv-worker/src/structuring.py`
- Modify: `workers/cv-worker/tests/test_qa.py`
- Modify: `workers/cv-worker/tests/test_structuring.py`

**Rules:**

- `validate_source_fidelity()` inside `build_whub_json()` already receives `compacted_text`; after integration this must be `sanitized_text`.
- `run_qa(... source_text=...)` must receive `sanitized_text`.
- `forbidden_candidate_name_parts()` should use raw text so surname/full identity can still be forbidden.
- Any source coverage extraction should ignore sanitizer-removed boilerplate/contact by design.

**Tests:**

- A source containing contact lines and business lines should pass coverage when the PDF contains business lines and omits contact lines.
- A source containing Hellowork boilerplate should not require that boilerplate in the PDF.
- A source missing a real business experience after rendering should still fail source coverage.

**Command:**

```bash
cd /root/whub-cv-factory/workers/cv-worker
pytest tests/test_qa.py::TestQA -v
pytest tests/test_structuring.py -k "fidelity or source" -v
```

**Expected:** PASS.

---

### Task 9: Add a realistic Hellowork fixture/smoke test

**Objective:** Prove the actual problem class is solved, not only micro-regex cases.

**Files:**

- Create or modify: `workers/cv-worker/tests/test_source_sanitizer.py`
- Possibly create fixture text under `workers/cv-worker/tests/fixtures/hellowork_cv_text.txt` if fixtures already exist; otherwise keep inline to avoid extra complexity.

**Fixture should include:**

- Candidate name/full identity in header.
- Email, phone, LinkedIn profile URL.
- Hellowork export/noise lines.
- Skills section with stack.
- Formation section.
- 2–3 experiences with dates, companies, mission bullets.
- Legitimate terms like `GitHub Actions`, `LinkedIn Ads`, `Th@Bot` if relevant.

**Assertions:**

- Contacts and Hellowork boilerplate gone.
- Business sections preserved.
- No raw sensitive value in report.
- Sanitized text length remains sufficient.
- Source section order preserved.

**Command:**

```bash
cd /root/whub-cv-factory/workers/cv-worker
pytest tests/test_source_sanitizer.py -v
```

**Expected:** PASS.

---

### Task 10: Run complete worker test suite and static compile

**Objective:** Verify no regression across structuring, QA, layout, renderer and worker taxonomy.

**Commands:**

```bash
cd /root/whub-cv-factory/workers/cv-worker
python -m py_compile src/*.py renderer/*.py scripts/*.py
pytest -q
```

**Expected:**

- `py_compile` exits 0.
- Full pytest exits 0.
- No new raw candidate data appears in failed test output.

If the full suite is too slow, still run all touched areas first and then the full suite before release. Do not claim operational readiness from targeted tests only.

---

### Task 11: Run renderer/preflight smoke locally

**Objective:** Confirm sanitization did not break the existing render/QA path.

**Commands:**

```bash
cd /root/whub-cv-factory/workers/cv-worker
python scripts/verify_whub_assets.py
pytest tests/test_rendering.py tests/test_renderer_overflow.py tests/test_layout_variants.py tests/test_main_layout_retry.py -q
```

**Expected:**

- Asset preflight passes.
- Rendering/layout tests pass.

---

### Task 12: Run one real end-to-end CV smoke before production

**Objective:** Prove the team can upload a CV and get a usable PDF after these changes.

**Precondition:** Clément approves using a real or sanitized test CV. If the CV contains personal data, do not paste raw content in chat/log summaries.

**Options:**

1. Preferred local smoke if an existing artifact script is still valid:

```bash
cd /root/whub-cv-factory
python artifacts/prod_e2e_zahia.py
```

2. If existing smoke is stale, create a temporary local smoke that:

- uses a local fixture PDF or text;
- runs extraction → sanitizer → structuring with configured model/fallback → render → QA;
- writes artifacts under `artifacts/sanitizer_smoke_<timestamp>/`;
- redacts any logs.

**Expected evidence:**

- `source_sanitized` event or local report with counts only.
- Structuring receives sanitized text.
- PDF QA has `contact_hits: []`.
- Source coverage has no missing business sections.
- PDF exists and opens.
- Layout status is `passed` or safe `draft` only if subjective layout warnings remain.

---

### Task 13: Independent review before release

**Objective:** Catch security/fidelity regressions before touching production.

**Review checklist:**

- No raw contact values stored in `cv_events`, `last_error`, logs, QA reports, sanitization reports or version JSON.
- Model prompt input is sanitized.
- Final PDF QA remains strict.
- Source fidelity compares against sanitized business source.
- Forbidden surname inference still uses raw source where needed.
- Hellowork boilerplate removal cannot erase whole experience blocks.
- False positive cases are covered by tests.
- No unrelated portal/Vercel/Supabase/auth changes.
- No secret/env var printed.

**Suggested command for diff review:**

```bash
cd /root/whub-cv-factory
git diff -- workers/cv-worker/src workers/cv-worker/tests workers/cv-worker/README.md
```

Do not proceed if review says `NO-GO`, `passed=false`, mentions raw PII leakage, source-fidelity regression, or unreviewed production changes.

---

### Task 14: Production release only after Clément approval

**Objective:** Make changes operational for the W hub team without hidden breakage.

**Precondition:** Clément explicitly says to release/deploy/restart.

**Release steps:**

```bash
cd /root/whub-cv-factory
git status --short
git add workers/cv-worker/src/source_sanitizer.py workers/cv-worker/src/main.py workers/cv-worker/src/structuring.py workers/cv-worker/src/qa.py workers/cv-worker/tests workers/cv-worker/README.md
git commit -m "feat(worker): sanitize CV source before structuring"
```

Then follow the worker production release runbook, not a blind restart:

```bash
sudo systemctl restart whub-cv-worker.service
sudo systemctl status whub-cv-worker.service --no-pager
journalctl -u whub-cv-worker.service -n 120 --no-pager
```

Post-restart verification:

- Worker starts cleanly.
- Startup preflight passes.
- No missing env/asset errors.
- A real portal request can move to `ready` or safe `draft_ready`.
- `cv_events` shows `source_sanitized` with safe counts.
- The generated PDF has no contact hits.

Do not deploy unrelated web app changes unless explicitly requested.

---

## Critical points to verify carefully

### 1. Sanitization must not break fidelity

The biggest risk is deleting useful business content while trying to remove contact noise. The sanitizer must be conservative. Removing a full line is safe only when the line is clearly contact/boilerplate. Otherwise remove just the contact substring and keep the rest.

Bad:

```text
Participation au développement de Th@Bot avec GitHub Actions
```

must remain.

Good removal:

```text
Email : jean.dupont@example.com
```

can disappear completely.

### 2. Address detection must be conservative

Addresses are hard. A line like `75008 Paris` in a header is probably contact. A line like `Mission chez BNP Paribas - Paris` is business content. Do not globally delete every postal code/city mention.

### 3. Hellowork boilerplate must be pattern-based, not layout-blind

Do not delete every repeated or short line. CVs often have short meaningful lines: `AWS`, `Docker`, `Scrum`, `2021`, `Paris`, `CDI`, `Freelance`.

### 4. Raw source must not leak through events/errors

If sanitizer reports include the exact removed value, the system still leaks PII, just in a different table. Reports must be counts and warning codes only.

### 5. Forbidden surname logic still needs raw context

If the raw header says `Jean Dupont`, the final PDF must not show `Dupont`. Sanitized text may remove the surname/header, so forbidden-name inference should still use raw text or a safe derived list in memory only.

### 6. PDF QA remains the final authority

Pre-sanitization reduces risk but does not replace post-render QA. The final PDF must still be extracted and checked. If PDF QA sees a contact leak, the job must fail, even if source sanitizer passed.

### 7. Source coverage must use sanitized business text

If source coverage uses raw text, it may flag removed contact/Hellowork lines as missing. If it uses sanitized text, it checks what matters: skills, formations, experiences, dates, missions, tools.

### 8. No QA threshold weakening

The right fix is context-aware detection + sanitization, not lowering QA. Keep hard failures hard.

---

## Advantages

- Reduces privacy risk because the model does not see obvious candidate contact data.
- Makes Hellowork CVs much less noisy before structuring.
- Improves structuring quality because the model focuses on skills/experience instead of headers/export junk.
- Keeps the raw PDF available for internal audit without exposing it to the model unnecessarily.
- Maintains W hub fidelity because QA still validates business content coverage.
- Reduces false positives by distinguishing real contact surfaces from technical/business words.
- Gives ops useful metrics through safe counts: number of emails/phones/URLs removed, without leaking values.
- Keeps final safety strong because PDF QA remains strict after rendering.

---

## Inconvénients / tradeoffs

- More complexity in the worker pipeline: raw text, sanitized text, safe report and forbidden identity terms must be handled carefully.
- Regex-based sanitization can create edge cases, especially addresses and unusual portfolio/project names.
- If sanitizer is too aggressive, it can silently damage source fidelity unless coverage tests catch it.
- If sanitizer is too conservative, some contact data may still reach the model, though post-structuring/PDF QA should block final delivery.
- Hellowork boilerplate patterns may evolve, so tests/fixtures will need maintenance.
- Event/report schema changes may require ops discipline to avoid logging raw values during debugging.
- A real E2E smoke is required before release; unit tests alone are not enough.

---

## Decisions confirmed by Clément

1. Remove **all personal/project URLs before structuring**, including portfolio, GitHub, LinkedIn, project demo/source links and website links. Preserve only the project name and the candidate's contribution sentence when that information is useful business content.
2. Hellowork-specific metadata such as availability, TJM/salary, desired contract, permit, mobility and ATS-style qualification details must stay **out of the client-facing CV** and do not need internal preservation in this pipeline, because W hub already has those details in the ATS. The worker's job here is strictly to produce the CV.

## Remaining open questions

1. For candidate address/location, do we keep broad localisation facts like `Paris / Remote / mobilité France` when they are part of the candidate positioning, while removing exact street address? My recommendation: yes, but not if the information is clearly just Hellowork/ATS metadata.
2. Should `source_sanitized` counts be visible in the portal UI to reassure users, or only stored in `cv_events` for ops? My recommendation: ops only for now; avoid cluttering the team UI.
3. Do we treat a CV that needs heavy sanitization as `draft_ready` with warning, or normal `ready` if final QA passes? My recommendation: normal `ready` if contact/fidelity/layout QA passes; heavy sanitization count is an internal ops warning, not a user-facing issue.

---

## Final validation checklist before saying “operational”

- `pytest tests/test_source_sanitizer.py -v` passes.
- `pytest tests/test_structuring.py -v` passes.
- `pytest tests/test_qa.py -v` passes.
- `pytest tests/test_draft_ready.py tests/test_main_error_taxonomy.py -v` passes.
- `python -m py_compile src/*.py renderer/*.py scripts/*.py` passes.
- Full `pytest -q` passes.
- Asset preflight passes.
- One realistic Hellowork-like smoke proves contact/Hellowork removal + business preservation.
- One real/generated PDF smoke proves final PDF has `contact_hits: []` and source coverage passes.
- Review confirms no raw PII in reports/events/errors/logs.
- Clément approves production release.
- Worker restart is verified via `systemctl` and journal.
- W hub team can submit a CV and receive `ready`/`draft_ready` with a downloadable PDF.

---

## Implementation order summary

1. Tests for `source_sanitizer`.
2. Implement `source_sanitizer.py`.
3. Wire sanitizer in `main.py` before `build_whub_json`.
4. Make JSON contact detection contextual and category-based.
5. Stop silently continuing on real residual JSON contact leaks.
6. Lock PDF QA false-positive semantics.
7. Add safe `source_sanitized` event and taxonomy coverage.
8. Align source fidelity with sanitized text.
9. Add Hellowork realistic fixture/smoke.
10. Run full tests and compile.
11. Run renderer/preflight/local E2E smoke.
12. Independent review.
13. Production release only after explicit approval.
