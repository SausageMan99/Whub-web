# W hub CV Factory Layout Intelligence Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Make the worker behave like a layout-aware W hub CV operator: detect ugly-but-technically-valid PDF layouts, rerender with safe non-destructive options, and never mark sparse/dense/orphaned CVs as `ready` silently.

**Architecture:** Keep source fidelity untouched. Add deterministic layout intelligence around existing `structured -> render_pdf -> run_qa` flow: pre-render layout option selection, post-render PDF metrics, safe retry option builder, and stronger QA codes. Renderer changes stay non-semantic and only influence placement/page breaks.

**Tech Stack:** Python worker in `/root/whub-cv-factory/workers/cv-worker`, PyMuPDF QA, external renderer `/root/.hermes/scripts/whub_cv_renderer.py`, pytest.

---

## Non-negotiables

Do not rewrite, summarize, drop, or reorder candidate facts. Contact/fidelity/source coverage remain hard blockers. Layout intelligence can only choose grouping, break hints, density thresholds, and render retry options. Do not restart production worker until final gates pass and Clément explicitly approves release.

## Current baseline

Relevant files:
- Worker orchestration: `workers/cv-worker/src/main.py`
- Layout options: `workers/cv-worker/src/layout_packing.py`
- QA/layout classifier: `workers/cv-worker/src/qa.py`
- Retry safety: `workers/cv-worker/src/layout_retry.py`
- Renderer wrapper: `workers/cv-worker/src/rendering.py`
- External renderer: `/root/.hermes/scripts/whub_cv_renderer.py`
- Tests: `workers/cv-worker/tests/test_layout_packing.py`, `test_qa_layout.py`, `test_main_layout_retry.py`, `test_renderer_overflow.py`

Existing useful behavior:
- `build_layout_packing_options()` already emits `_layout` options.
- `run_qa()` already emits soft layout codes.
- Worker can rerender once on safe layout warnings.
- Oussama v2 proved grouping beats forced experience pages.

Known gap:
- There is no explicit reusable “layout intelligence report” that measures page useful density and maps QA warnings to safe retry choices.
- Retry currently forces `force_experiences_new_page=True`, which can recreate sparse-page failures.
- QA lacks a direct general check for non-last pages with low used-height ratio and tiny continuation tails.
- Renderer behavior for skill overflow is patched externally but not covered by a targeted test in repo.

---

### Task 1: Add deterministic PDF layout metrics and sparse-page detection

**Objective:** Expose page-level visual metrics and fail/draft on sparse non-last pages, not only sparse final pages.

**Files:**
- Modify: `workers/cv-worker/src/qa.py`
- Test: `workers/cv-worker/tests/test_qa_layout.py`

**Implementation guidance:**
Add a helper such as `collect_page_layout_metrics(doc)` returning per page: `page`, `char_count`, `block_count`, `used_ratio`, `blank_after_pt`, `starts_with_suite`, `has_experience_heading`.
Use it inside `find_layout_issues()`.
Emit `page_too_sparse` for non-first, non-last pages when:
- `used_ratio <= 0.40` and `char_count <= 900`, or
- page starts with `(suite)` / `Missions (suite)` / `Livrables clés (suite)` and `used_ratio <= 0.45`, or
- `blank_after_pt >= 430` and `char_count <= 1200`.
Keep last-page logic as-is but reuse the helper.

**Tests:**
Create a PyMuPDF fixture with 3 pages where page 2 has only a short continuation block and lots of blank space. Assert `find_layout_issues()` emits `page_too_sparse` for page 2.
Also assert a normal medium page with ~0.55 used ratio is not flagged.

**Verification:**
Run `PYTHONPATH=. pytest tests/test_qa_layout.py -q`.

---

### Task 2: Replace retry hardcoding with safe retry option builder

**Objective:** Make layout retry choose grouping vs anti-crowding based on actual issue codes instead of always forcing new experience pages.

**Files:**
- Create or modify: `workers/cv-worker/src/layout_intelligence.py`
- Modify: `workers/cv-worker/src/main.py`
- Test: `workers/cv-worker/tests/test_main_layout_retry.py` or new `test_layout_intelligence.py`

**Implementation guidance:**
Create `build_layout_retry_options(base_options, qa_report)`.
Rules:
- For `page_too_sparse`, `last_page_sparse`, `page_underfilled_with_next_experience_fit`: set `force_experiences_new_page=False`, clear `force_page_break_before_experience_indexes`, keep `anti_crowding=True`, use moderate density (`page_dense_char_threshold >= 2850`, `max_used_ratio >= 0.86`).
- For `page_too_dense`, `experience_orphan_heading`, `bad_page_break`: keep/enable anti-crowding, add or preserve break hints, but do not force every experience to a new page unless no sparse codes are present.
- Sparse codes win over forced-new-page behavior.
- Never mutate `structured` content.
Update `main.py` retry branch to call this builder instead of inline hardcoded options.

**Tests:**
Unit-test the builder for sparse report, dense report, and mixed sparse+dense report. Assert sparse report clears forced breaks.

**Verification:**
Run `PYTHONPATH=. pytest tests/test_main_layout_retry.py tests/test_layout_packing.py -q`.

---

### Task 3: Cover renderer skill-overflow anti-tail behavior

**Objective:** Prevent the renderer from starting an experience too low after skill overflow and creating a tiny continuation page.

**Files:**
- Modify: `/root/.hermes/scripts/whub_cv_renderer.py`
- Test: `workers/cv-worker/tests/test_renderer_overflow.py`

**Implementation guidance:**
Renderer already has `overflow_page_lacks_experience_room` local patch. Add/adjust a test that builds a CV with enough skills to overflow page 1 and a long first experience. Assert generated PDF does not contain a page with only `Livrables clés (suite)`/`Missions (suite)` and < 900 chars before the next main experience page.
If needed, keep the renderer threshold option `max_skill_overflow_experience_start_y` default around 450.

**Verification:**
Run `PYTHONPATH=. pytest tests/test_renderer_overflow.py -q`.

---

### Task 4: Add Oussama-style end-to-end smoke fixture

**Objective:** Lock the real product regression: Oussama-like medium faithful CV should render as grouped 4–5 pages with no layout issues.

**Files:**
- Use existing: `/tmp/oussama_prod_structured.json` if available only as local smoke input; do not commit private candidate facts unless already in test fixture.
- Prefer synthetic fixture in `workers/cv-worker/tests/fixtures/medium_faithful_layout.json`
- Test: `workers/cv-worker/tests/test_layout_intelligence_smoke.py`

**Implementation guidance:**
Use synthetic but structurally similar data: many skills, 7 experiences, first 3 long, later short. Assert:
- `build_layout_packing_options()` does not force artificial experience pages.
- Rendered PDF has no page with used ratio < 0.40 except possibly final page if > 900 chars.
- `run_qa()` passes or only yields acceptable draft warnings depending thresholds; target should be pass.

**Verification:**
Run targeted smoke plus full suite.

---

### Task 5: Final gates, review, release handoff

**Objective:** Produce a release-ready implementation without deploying prematurely.

**Commands:**
From `workers/cv-worker`:
```bash
PYTHONPATH=. pytest -q
python -m py_compile src/*.py /root/.hermes/scripts/whub_cv_renderer.py
python /root/.hermes/skills/user-workflows/whub-client-cv-generator/scripts/verify_whub_assets.py
```

Then from repo root:
```bash
git diff --stat
git status --short
```

**Final review:**
Use a read-only reviewer to inspect:
- no content mutation;
- sparse retry cannot worsen pages;
- QA codes are soft vs hard correctly;
- no production restart or secrets.

**Commit scope:**
Stage only worker files/tests and, if accepted, document that `/root/.hermes/scripts/whub_cv_renderer.py` is an external production script not tracked by this Git repo. If a durable renderer release is needed, decide whether to vendor it into repo or manage it as Hermes script separately.
