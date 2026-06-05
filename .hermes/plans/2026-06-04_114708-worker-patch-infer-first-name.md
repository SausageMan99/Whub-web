# Worker patch: infer candidate first name from source when portal omits it

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task. Do not deploy or restart the worker until all tests, local smoke, and independent review are green, then require Clément's explicit release approval.

**Goal:** When the portal creates a request without filling `candidate_first_name` (as in incident 82c6a49f), the worker should attempt to infer the first name from the source PDF text using conservative pattern matching. If inference is confident, use it to populate the first-name-only display and the forbidden-identity list. If inference is uncertain, fail safely with a clear error instead of letting the LLM leak the full name.

**Architecture:** Extend `infer_forbidden_candidate_identity_terms` in `src/structuring.py` with a new sub-path that activates only when `candidate_first_name` is empty. The existing first-name-provided path remains untouched. The new path scans the first 50 lines of the source (broader than the current 12-line header zone), applies the existing `_looks_like_standalone_identity_line` heuristic, and tries to extract a (first, surname) pair. If confident, the function returns the forbidden terms as usual. If not confident, the function returns a sentinel that the caller translates into a clear `failed` status with a new error category.

**Tech Stack:** Python 3.11, pytest, existing structuring module, existing identity heuristics.

---

## Current context

In incident `82c6a49f-4a66-4b2b-8a2d-22c18c9d048c`:

- The CV `HODARD Florian_CV.pdf` was uploaded with `candidate_first_name=""`.
- The portal correctly emitted the request with an empty first name field.
- The new sanitizer removed 1 email, 1 phone, 4 URLs, 2 Hellowork lines. It does not touch names.
- The primary M3 model returned valid JSON in 5 min 4s.
- The fallback gpt-5.5 codex returned valid JSON in 44s.
- Both structured outputs were rejected by `validate_source_fidelity` with `identity_leak` because the JSON contained the surname `HODARD` (and/or the full name `FLORIAN HODARD`) that the worker had no way to strip without a first-name reference.
- Final public `last_error` was the safe `transient_model_failure` message because both primary and fallback failed.

Root cause: when `candidate_first_name` is empty, the current code path in `infer_forbidden_candidate_identity_terms` (structuring.py:708-725) only inspects the first 12 lines of the source and uses the heuristic `_looks_like_standalone_identity_line`. The HODARD CV has the name at line 47 (Aspose-generated PDF with skills before the name block), so the heuristic returns `[]`. `enforce_client_first_name(data, "")` then does nothing, the LLM puts the full name in the structured JSON, and the identity check blocks the job.

Existing relevant code in `src/structuring.py`:
- `_IDENTITY_LINE_REJECT_TOKENS` (lines 562-607) already lists business words to reject (gestion, sql, server, data, analyst, engineer, etc.).
- `_looks_like_standalone_identity_line` (lines 628-638) is the existing heuristic. It rejects lines containing `@`, URLs, phone numbers, digits, `&`, and rejects any token in the reject list. Requires 2-4 tokens, all starting with an uppercase letter.
- `_identity_tokens` (line 509) splits a line into alphanumeric tokens.
- `_token_starts_with_uppercase_letter` (line 623) checks if a token starts with a capital letter.
- `infer_forbidden_candidate_identity_terms` (line 677) is the entry point.

The patch is small and targeted: add a helper that runs only when the first name is empty, scans a wider range, and applies the existing heuristic with a few small additional rules for the common failure patterns (Mr./Mme. prefix, multi-line name, name-after-title).

---

## Non-negotiable acceptance criteria

1. The patch activates only when `candidate_first_name` is empty. The first-name-provided path is byte-for-byte unchanged.
2. The inference scans up to 50 lines of the source (broader than the current 12) to handle layouts where the name is below skills/competences.
3. The inference reuses the existing `_looks_like_standalone_identity_line` heuristic. No new ad-hoc pattern matching that bypasses the existing reject list.
4. If the inference finds a confident (first, surname) pair, the function returns the surname as a forbidden term and the worker uses the first name in `enforce_client_first_name` (via a small wiring change in `main.py`).
5. If the inference cannot find a confident pair, the worker fails the job with a new error category `missing_candidate_first_name` and a clear public message. It does NOT silently accept an unreliable inference.
6. The inference does not invent names. It only returns a name if the source clearly contains a "Prénom NOM" pattern that matches the existing heuristic.
7. Real CVs with the name in the first 12 lines (LinkedIn-style, classic Word template) continue to work as today.
8. Real CVs with the name after skills (Aspose-generated, Hellowork exports) now succeed.
9. The existing 251-test suite remains green. New tests cover the inference path.
10. No unrelated changes: no web, no Supabase schema, no portal, no Vercel.

---

## Files likely to change

Modify:
- `workers/cv-worker/src/structuring.py` — add `_infer_first_name_from_source` helper, extend `infer_forbidden_candidate_identity_terms` to call it when first_name is empty, add a sentinel return for "inference failed", add `missing_candidate_first_name` to error taxonomy.
- `workers/cv-worker/src/main.py` — when the sentinel is detected, route the job to `fail_job` with the new error category.
- `workers/cv-worker/tests/test_structuring.py` — add tests for the new inference path.
- `workers/cv-worker/tests/test_main_error_taxonomy.py` — add a test that the new `missing_candidate_first_name` category is properly classified.

Do not change during this plan unless implementation proves necessary:
- The renderer, the renderer JSON contract, the QA PDF module, the sanitizer, Supabase, Vercel, the portal web.

---

## Detailed implementation plan

### Task 1: Add failing tests for the inference path

**Objective:** Define the expected behavior before touching implementation.

**Files:**
- Modify: `workers/cv-worker/tests/test_structuring.py`

Add tests in a new class `TestInferFirstNameFromSource` (or grouped under existing classes) that:

1. **HODARD-style layout (name at line ~47, after skills)**: source with skills first, then `FLORIAN HODARD`, then title. Assert that `infer_forbidden_candidate_identity_terms(source, "")` returns `["HODARD"]` (or `["Hodard"]` matching the source casing). Assert that the new helper `_infer_first_name_from_source(source)` returns `"FLORIAN"`.

2. **Classic layout (name at line 1)**: source starts with `Jean Dupont` directly. Existing behavior preserved. Assert forbidden list contains `["Dupont"]`.

3. **Mr. prefix**: source has `Mr. Jean DUPONT`. Assert the helper extracts `Jean` as first name and `DUPONT` as forbidden.

4. **Mme. / M. prefix**: same as Mr. but with `Mme.` and `M.`. Assert correct extraction.

5. **Hyphenated first name**: `Jean-Philippe DUPONT`. Assert the helper returns `Jean-Philippe` as first name.

6. **Anonymized CV with no name line**: source has no clear identity line anywhere in 50 lines. Assert the helper returns `None` (sentinel for "cannot infer") and `infer_forbidden_candidate_identity_terms(source, "")` returns `[]` AND a separate sentinel that the caller can detect. (Implementation choice: return `(forbidden, inferred_first_name_or_None)` tuple, OR raise a custom exception, OR return a special sentinel value. The plan favors a custom exception class `_CandidateFirstNameInferenceError` that propagates cleanly.)

7. **Title before name (INGÉNIEUR DEVOPS then Florian HODARD)**: source has `INGÉNIEUR DEVOPS\nFlorian HODARD\n...`. Assert the helper finds the second line, not the first. (Use the existing `_IDENTITY_LINE_REJECT_TOKENS` which already includes "engineer" via "analyst/engineer"; we need to verify "DEVOPS" is also rejected or filtered out.)

8. **Multi-line identity (Jean on one line, DUPONT on next)**: source has `Jean\nDUPONT`. Assert the helper joins them.

9. **Business sentence rejected**: source has `INGÉNIEUR DE PRODUCTION GESTION FLUX`. Assert the helper does NOT match this as an identity (because tokens are in the reject list).

10. **Skills section rejected**: source has `Programmation / Langages C#, SQL Server`. Assert no false positive.

11. **Email in identity line rejected**: source has `Jean Dupont <jean@example.com>`. Assert no false positive (line contains `@`).

12. **Empty source**: source is `""`. Assert the helper returns None and the caller fails safely.

13. **Name with particle "de"**: source has `Charles de GAULLE`. Assert the helper returns `Charles` as first name and `GAULLE` as forbidden (the `de` particle is filtered out by `_KNOWN_FIRST_IDENTITY_BOUNDARY_TOKENS` which already includes `de`).

14. **Double surname hyphenated**: `Marie CURIE-SKLODOWSKA`. Assert the helper returns `Marie` and `CURIE-SKLODOWSKA` as forbidden.

15. **Single-word name (just first name)**: source has only `FLORIAN` with no surname. Assert the helper returns `None` because a single token is not a confident identity pair.

**Command:**

```bash
cd /root/whub-cv-factory/workers/cv-worker
PYTHONPATH=".:.venv/lib/python3.11/site-packages" pytest tests/test_structuring.py -k "InferFirstName or infer_first_name or identity_terms" -v
```

**Expected before implementation:** Tests fail because `_infer_first_name_from_source` does not exist.

---

### Task 2: Implement `_infer_first_name_from_source` and wire it

**Objective:** Add a conservative first-name inference helper that activates only when the first name is empty.

**Files:**
- Modify: `workers/cv-worker/src/structuring.py`

Implementation details:

```python
class _CandidateFirstNameInferenceError(Exception):
    """Raised when the source has no confident Prénom NOM pattern to infer from."""

    def __init__(self, scanned_lines: int, reason: str):
        self.scanned_lines = scanned_lines
        self.reason = reason
        super().__init__(f"cannot infer candidate first name: {reason}")


def _infer_first_name_from_source(source_text: str, scan_limit: int = 50) -> tuple[str, list[str]]:
    """Return (inferred_first_name, forbidden_post_first_tokens) from source text.

    Conservative pattern matching for CVs that don't put the candidate name in
    the first 12 lines. Reuses _looks_like_standalone_identity_line and
    _IDENTITY_LINE_REJECT_TOKENS. Returns ("", []) if no confident match is
    found within scan_limit lines. Raises _CandidateFirstNameInferenceError
    if called with an empty source so the caller can fail safely.

    The scan_limit is intentionally bounded. CVs where the name is on page 2+
    are out of scope for this patch; the portal fix is the right answer there.
    """
    if not source_text or not source_text.strip():
        raise _CandidateFirstNameInferenceError(0, "empty source text")

    lines = (source_text or "").splitlines()[:scan_limit]
    candidates: list[tuple[int, str, str, list[str]]] = []  # (priority, line, first, forbidden)

    for line_index, line in enumerate(lines):
        stripped = line.strip()
        if not stripped:
            continue
        if _is_document_identity_header(stripped):
            continue
        # Try single-line identity
        if _looks_like_standalone_identity_line(stripped):
            tokens = _identity_tokens(stripped)
            if len(tokens) >= 2:
                first = tokens[0]
                forbidden = [t for t in tokens[1:] if not _is_document_identity_token(t)]
                if forbidden:
                    # Lower priority for tokens that look like common job titles
                    priority = sum(1 for t in forbidden if _normalize_for_fidelity(t) in _IDENTITY_LINE_REJECT_TOKENS)
                    candidates.append((priority, stripped, first, forbidden))
        # Try multi-line identity: first name on this line, surname on next non-empty line
        if line_index + 1 < len(lines):
            next_line = lines[line_index + 1].strip()
            if next_line and _looks_like_standalone_identity_line(next_line):
                current_tokens = _identity_tokens(stripped)
                next_tokens = _identity_tokens(next_line)
                if len(current_tokens) == 1 and len(next_tokens) == 1:
                    first = current_tokens[0]
                    forbidden = [next_tokens[0]] if not _is_document_identity_token(next_tokens[0]) else []
                    if forbidden:
                        candidates.append((0, stripped + " | " + next_line, first, forbidden))

    if not candidates:
        return ("", [])

    # Pick the candidate with the lowest reject-token priority, then earliest position
    candidates.sort(key=lambda c: (c[0], lines.index(c[1]) if c[1] in lines else 0))
    _, _, first, forbidden = candidates[0]
    return (first, forbidden)
```

Wire it into `infer_forbidden_candidate_identity_terms`:

```python
def infer_forbidden_candidate_identity_terms(source_text: str, candidate_first_name: str | None = None) -> list[str]:
    """..."""
    allowed_first = normalize_candidate_first_name(candidate_first_name)
    identity_line = ""
    if allowed_first:
        # ... existing code unchanged ...
    else:
        # Without a trusted first name, attempt a conservative inference from
        # the first 50 lines. If inference succeeds, the first token becomes
        # the allowed first name and subsequent tokens become forbidden.
        try:
            inferred_first, inferred_forbidden = _infer_first_name_from_source(source_text or "")
        except _CandidateFirstNameInferenceError:
            return []  # empty source, no inference possible
        if not inferred_first or not inferred_forbidden:
            return []  # no confident inference
        # Re-run the first-name-provided path with the inferred first name.
        # This reuses the existing logic and keeps the inference path testable.
        return infer_forbidden_candidate_identity_terms(source_text, inferred_first)
```

The recursive call is bounded: the inferred path is only entered if `inferred_forbidden` is non-empty, and the recursive call passes a non-empty first name, so it takes the first-name-provided path which doesn't call `_infer_first_name_from_source` again. No infinite recursion.

**Command:**

```bash
cd /root/whub-cv-factory/workers/cv-worker
PYTHONPATH=".:.venv/lib/python3.11/site-packages" pytest tests/test_structuring.py -k "InferFirstName or infer_first_name or identity_terms" -v
```

**Expected after implementation:** All inference tests pass.

---

### Task 3: Wire inferred first name into `main.py` for `enforce_client_first_name`

**Objective:** When the inference succeeds, the worker should pass the inferred first name to `enforce_client_first_name` so the LLM output's `name` field gets stripped to first-name-only.

**Files:**
- Modify: `workers/cv-worker/src/main.py`

Current code (line 117-118):
```python
structured = build_whub_json(sanitized_text, job.get("instructions") or "", comments_for_prompt, job.get("candidate_first_name"))
enforce_client_first_name(structured, job.get("candidate_first_name"))
```

Wanted behavior:
```python
effective_first_name = job.get("candidate_first_name") or None
if not effective_first_name:
    # Try to infer the first name from the source so we can enforce first-name-only display
    try:
        inferred_first, _ = _infer_first_name_from_source(text)
        if inferred_first:
            effective_first_name = inferred_first
    except _CandidateFirstNameInferenceError:
        pass

structured = build_whub_json(sanitized_text, job.get("instructions") or "", comments_for_prompt, effective_first_name)
enforce_client_first_name(structured, effective_first_name)
```

The `forbidden_candidate_name_parts(job.get("candidate_first_name"), text)` call (line 125 in main.py) does NOT need to change: it already uses raw text and the existing `infer_forbidden_candidate_identity_terms` (now with the recursive inference path) will pick up the inferred first name automatically.

**Test:**

Add a test in `tests/test_draft_ready.py`:
- `test_process_job_infers_first_name_when_portal_omits_it` that monkeypatches:
  - `extract_pdf_text` returns a HODARD-like source (name at line ~47).
  - `build_whub_json` captures the `candidate_first_name` argument.
  - Asserts the captured first name is `"FLORIAN"` (inferred from the source).
  - `enforce_client_first_name` is called with `"FLORIAN"`.

**Command:**

```bash
cd /root/whub-cv-factory/workers/cv-worker
PYTHONPATH=".:.venv/lib/python3.11/site-packages" pytest tests/test_draft_ready.py -k "infer_first_name or first_name" -v
```

**Expected after implementation:** The new test passes; existing `process_job` tests still pass.

---

### Task 4: Add `missing_candidate_first_name` error category

**Objective:** When inference fails (e.g. anonymized CV), the worker should fail with a clear, safe public message.

**Files:**
- Modify: `workers/cv-worker/src/structuring.py` — add to `STRUCTURING_ERROR_PUBLIC_MESSAGES` and `classify_structuring_error`.
- Modify: `workers/cv-worker/tests/test_main_error_taxonomy.py` — add a test.

Implementation:

```python
STRUCTURING_ERROR_PUBLIC_MESSAGES = {
    # ... existing entries ...
    "missing_candidate_first_name": "Prénom candidat absent et non inférable depuis le CV source.",
}

# In classify_structuring_error, add a new branch:
elif re.search(r"\b(missing_candidate_first_name|candidate first name inference|premiers nom candidat|inferable)\b", normalized):
    category = "missing_candidate_first_name"
```

**Test:**

In `tests/test_main_error_taxonomy.py`:
- `test_classifies_missing_candidate_first_name_error_with_safe_message`
- `test_process_job_missing_candidate_first_name_calls_fail_job_with_safe_public_message`

**Command:**

```bash
cd /root/whub-cv-factory/workers/cv-worker
PYTHONPATH=".:.venv/lib/python3.11/site-packages" pytest tests/test_main_error_taxonomy.py -v
```

**Expected:** New tests pass; existing taxonomy tests pass.

---

### Task 5: Full regression + smoke

**Objective:** Verify nothing else broke.

**Commands:**

```bash
cd /root/whub-cv-factory/workers/cv-worker
PYTHONPATH=".:.venv/lib/python3.11/site-packages" pytest -q
python -m py_compile src/structuring.py src/main.py
```

**Expected:** 251 + new tests pass; no compile errors.

Then run a HODARD smoke locally using the same `sanitizer_smoke_20260604_*` pattern:
- Create `/root/whub-cv-factory/artifacts/smoke_hodard_<timestamp>/smoke.py` that:
  - Loads the HODARD source from the downloaded `/tmp/hodard_source.pdf`.
  - Runs `extract_pdf_text → sanitize_source_text → build_whub_json (stubbed runner) → enforce_client_first_name → render_pdf → run_qa`.
  - Uses `infer_forbidden_candidate_identity_terms(text, "")` directly and asserts the result contains `HODARD`.
  - Uses `_infer_first_name_from_source(text)` directly and asserts it returns `FLORIAN`.
- Save the resulting PDF and a summary.

**Expected smoke output:**
- `infer_forbidden_candidate_identity_terms(text, "")` returns `["HODARD"]` (or `["Hodard"]`).
- `_infer_first_name_from_source(text)` returns `("FLORIAN", ["HODARD"])`.
- Rendered PDF has `contact_hits=[]`, `has_logo=True`, `has_watermark=True`, and `name` field starts with `FLORIAN` only.

---

### Task 6: Independent review

**Objective:** Catch any security/fidelity regression before touching production.

**Review checklist:**

- The first-name-provided path is byte-for-byte unchanged. Verify by diff.
- The new helper only activates when `candidate_first_name` is empty. Verify by reading the call site.
- The new helper does not introduce new pattern matching that bypasses `_IDENTITY_LINE_REJECT_TOKENS`. Verify the helper reuses it.
- The new error category is safe (no raw value leakage in the public message).
- The recursive call in `infer_forbidden_candidate_identity_terms` is bounded (no infinite loop).
- No unrelated changes outside the worker.

**Command:**

```bash
cd /root/whub-cv-factory
git diff -- workers/cv-worker/src/structuring.py workers/cv-worker/src/main.py
```

---

### Task 7: Production release only after Clément approval

**Precondition:** Clément explicitly says to release.

**Release steps:**

```bash
cd /root/whub-cv-factory
git status --short
git add workers/cv-worker/src/structuring.py workers/cv-worker/src/main.py workers/cv-worker/tests/test_structuring.py workers/cv-worker/tests/test_draft_ready.py workers/cv-worker/tests/test_main_error_taxonomy.py
git commit -m "feat(worker): infer candidate first name from source when portal omits it"
sudo systemctl restart whub-cv-worker.service
sudo journalctl -u whub-cv-worker.service -n 50 --no-pager
```

Post-restart verification:
- Worker starts cleanly.
- No missing env/asset errors.
- A real request with empty `candidate_first_name` either:
  - Succeeds because the inference found the name in the source (most cases), or
  - Fails with the new `missing_candidate_first_name` category and a clear public message (rare case, e.g. anonymized CV).

---

## Critical points to verify carefully

1. **Recursion safety**: the inference path calls `infer_forbidden_candidate_identity_terms` recursively with the inferred first name. The first-name-provided path does NOT call `_infer_first_name_from_source`, so the recursion is bounded at depth 1. Verify by reading the call graph.

2. **Empty first_name from portal vs from worker**: the patch only triggers when `job.get("candidate_first_name")` is `None` or `""`. An explicit empty string from the portal means "the user did not provide a first name", which is the case we want to handle. An explicit non-empty first name from the portal takes the existing path untouched.

3. **Inference must fail loud, not silent**: if the helper cannot find a confident (first, surname) pair, it returns `("", [])` and the worker fails the job with `missing_candidate_first_name`. The worker must NOT silently continue and let the LLM produce a full-name JSON. The current `infer_forbidden_candidate_identity_terms` returning `[]` causes the identity check to be weak, but the LLM still produces a full name. The fix is to use the new error category to fail the job at `validate_source_fidelity` time.

   Wait — actually, looking at the code more carefully: when `infer_forbidden_candidate_identity_terms` returns `[]` and the structured JSON has a full name, `validate_source_fidelity` does NOT have any forbidden term to check against, so it does NOT flag identity_leak. The identity_leak in incident 82c6a49f was flagged by... hmm, let me check `validate_source_fidelity` more carefully.

   Actually, looking at the journal output: `primary validation failed category=identity_leak`. This means `validate_source_fidelity` DID flag it. The reason is that `validate_source_fidelity` doesn't just check against `forbidden_identity_terms` — it also checks the structured output for any surname that appears in the source. If the source has "HODARD" and the JSON has "HODARD" in the name field, the function flags it.

   So the current `infer_forbidden_candidate_identity_terms` returning `[]` doesn't prevent the identity_leak detection — it just means the worker had no way to pre-strip the surname. The new inference path fixes this by populating the forbidden list with the inferred surname.

4. **Test coverage of false positives**: the most dangerous failure mode is the helper inferring the WRONG name. For example, on a CV with `JANE SMITH Senior Developer`, the helper might infer "JANE" and "SMITH" correctly, but on a CV with `JAVA SPRING DEVELOPER`, the helper might wrongly infer "JAVA" and "SPRING". The reject list already covers "java"-like tokens? Let me check... the reject list has `sql`, `server`, `data`, `analyst`, `engineer`, `responsable`, `applicatif`, `developpeur`, `architecte`, `senior`, but NOT `java`, `spring`, `devops`. The patch must add common tech-stack words to the reject list OR rely on the multi-word heuristic to catch them.

   Actually, `_looks_like_standalone_identity_line` rejects lines with `&`, digits, `@`, URLs, phone numbers. The pattern requires 2-4 tokens, all starting with uppercase. `JAVA SPRING DEVELOPER` is 3 tokens all starting with uppercase. If `developpeur` is in the reject list (yes, it is), the function returns False. So `JAVA SPRING` alone is 2 tokens both uppercase, and not in the reject list. The helper would infer "JAVA" as first name and "SPRING" as forbidden. This is a false positive.

   Mitigation: add `java`, `spring`, `devops`, `docker`, `kubernetes`, `aws`, `azure`, `python`, `javascript`, `typescript`, `react`, `angular`, `vue`, `node`, `c#`, `c++`, `php`, `ruby`, `golang`, `rust`, `aws`, `gcp`, `terraform`, `ansible`, `jenkins`, `git`, `github`, `gitlab`, `jira`, `confluence`, `agile`, `scrum`, `kanban`, `devops`, `sre` to the reject list, OR add a stronger heuristic that requires the second token to look like a surname (e.g. starts with uppercase, length >= 3, not in a known tech-stack list).

   For the patch scope, the simpler fix is to add common tech-stack words to `_IDENTITY_LINE_REJECT_TOKENS`. This is a 5-line change in `structuring.py`.

5. **The HODARD CV is single-page but the name is at line 47**: the patch must scan at least 50 lines to catch this case. The current scan is 12 lines.

6. **The patch must not regress the existing identity inference for CVs where first_name IS provided**: the existing tests `test_*identity*` in `tests/test_structuring.py` cover this. They must all pass after the patch.

---

## Advantages

- Covers the incident class `82c6a49f` and similar cases where the portal omits the first name.
- Reuses the existing identity heuristic, the existing reject list, and the existing error taxonomy.
- Fails safely with a clear public message when inference is uncertain, rather than silently producing a full-name PDF.
- Bounded change: only the empty-first-name path is touched.
- No portal or web change required (the patch is defense-in-depth).

## Inconvénients / tradeoffs

- Not 100% coverage. Edge cases (anonymized CVs, single-name candidates, unusual layouts) will still fail with the new category.
- The scan limit (50 lines) is a heuristic. CVs where the name is on page 2 are out of scope.
- The reject list for tech-stack words is not exhaustive. Future CVs with rare tech tokens could trigger false positives.
- The recursive call adds a small overhead (one extra function call stack) for the empty-first-name path.
- The patch does not fix the root cause (portal not requiring first_name). It is a defense-in-depth measure.

## Open questions for Clément

1. For the smoke test, do you want me to use the existing `/tmp/hodard_source.pdf` (already downloaded for incident 82c6a49f) and produce a real PDF for visual inspection? Or skip the visual smoke and rely on programmatic QA?
2. For the release, do you want me to relaunch the failed job `82c6a49f` after the worker is restarted, or leave it as-is and let the portal team re-trigger it?
3. For the error category, do you prefer `missing_candidate_first_name` (technical) or `candidate_first_name_required` (more user-facing)? My recommendation: `missing_candidate_first_name` for ops, with a public message that says the same in French.

## Final validation checklist before saying "operational"

- New tests for the inference path pass.
- Existing 251 tests still pass.
- py_compile passes for `src/structuring.py` and `src/main.py`.
- HODARD smoke test produces a real PDF with the name `FLORIAN` only, `contact_hits=[]`, `has_logo=True`, `has_watermark=True`.
- A CV with no inferable first name (e.g. fully anonymized) fails with the new error category and a clear public message.
- Independent review returns GO.
- Clément approves the release.
- Worker restart is verified via `systemctl` and journal.
- W hub team can submit a CV with empty first name and either get a valid PDF (most cases) or a clear `missing_candidate_first_name` failure (rare cases).

## Implementation order summary

1. Tests for the inference path.
2. Implement `_infer_first_name_from_source` and wire it into `infer_forbidden_candidate_identity_terms`.
3. Wire inferred first name into `main.py` for `enforce_client_first_name`.
4. Add `missing_candidate_first_name` error category and tests.
5. Full regression + py_compile.
6. HODARD smoke test.
7. Independent review.
8. Production release only after explicit approval.
