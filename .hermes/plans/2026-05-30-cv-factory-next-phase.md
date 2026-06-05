# W hub CV Factory — Next Phase Implementation Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Make the internal W hub CV Factory fully autonomous for ~20 internal users and ~5–6 CV/day: upload a CV, remove candidate identity/contact details, preserve source content exactly unless explicit instructions say otherwise, and output a W hub PDF with communication-level layout quality.

**Architecture:** Keep the system simple: Next.js portal + Supabase + one Python worker + W hub renderer. Do not overbuild enterprise scaling. Invest in strict source fidelity, deterministic layout scoring, simple preview/correction loop, durable renderer/assets, and a clean internal UX.

**Tech Stack:** Next.js App Router, Supabase Auth/DB/Storage, Python worker, PyMuPDF QA, W hub ReportLab renderer, pytest, tsx tests, systemd.

---

## Product contract

The portal is not a CV rewriting tool. It is a faithful W hub layout assistant.

Default behavior:
- copy source CV content exactly after extraction normalization;
- remove full candidate identity/contact details: surname, phone, email, LinkedIn, GitHub/profile URLs, portfolio URLs, personal address;
- preserve mission locations, companies, dates, titles, stacks, achievements, formations and wording;
- apply W hub visual style, layout, margins, pagination and spacing.

Forbidden unless explicitly requested:
- rewriting bullets;
- summarizing;
- improving wording;
- inventing client-facing impact;
- dropping older experiences;
- changing titles/companies/dates;
- creating technical environments from tools mentioned in prose.

Target experience:
- Internal user uploads a CV, enters first name/title/instructions if needed, clicks generate.
- If safe and beautiful: status `ready`.
- If safe but visually imperfect: status `draft_ready`, downloadable with clear warnings and one-click correction request.
- If unsafe/factual/contact issue: status `qa_failed`, no client PDF released.

---

## Phase 1 — Finalize strict fidelity mode

### Task 1.1: Make the default mode explicit everywhere

**Objective:** Ensure portal, worker and prompts all express the same default: faithful copy, no rewrite.

**Files:**
- Modify: `apps/web/app/requests/new/intentions.ts`
- Modify: `workers/cv-worker/src/structuring.py`
- Modify tests: `apps/web/tests/upload.test.ts`, `workers/cv-worker/tests/test_structuring.py`

**Steps:**
1. Rename the default guided intention to something like `CV W hub fidèle — mise en page uniquement`.
2. Ensure generated instruction text says: preserve exact source wording, remove only contacts/name, do not rewrite unless explicitly requested.
3. Add a web test checking the default intention contains `sans reformulation` and `mise en page uniquement`.
4. Add a worker prompt test checking default prompt forbids rewrite/synthesis.
5. Run: `npm test` and `cd workers/cv-worker && PYTHONPATH=. pytest tests/test_structuring.py -q`.

**Done when:** Default portal requests cannot ambiguously mean “make the CV better”; they mean “make it W hub and faithful”.

### Task 1.2: Add source coverage gate for business sections

**Objective:** Block PDFs that are faithful for included lines but silently omit meaningful source sections.

**Files:**
- Modify: `workers/cv-worker/src/structuring.py`
- Modify: `workers/cv-worker/src/qa.py`
- Tests: `workers/cv-worker/tests/test_structuring.py`, `workers/cv-worker/tests/test_qa.py`

**Steps:**
1. Extend source coverage extraction for sections like `Projets`, `Réalisations`, `Certifications`, `Langues`, `Compétences`, `Autres` when business-relevant.
2. Allow only explicit exclusions: contact, surname/full name, profile links, address, privacy boilerplate, page markers.
3. Add tests where a source has `Exemples de réalisations professionnelles` and output omits it: must fail.
4. Add tests where only phone/email/LinkedIn/address are omitted: must pass.
5. Run full worker tests.

**Done when:** A CV can’t pass just because every rendered bullet is source-backed; it must also cover the meaningful source.

### Task 1.3: Classify explicit edit instructions separately

**Objective:** Allow modifications only when the user explicitly asks, without weakening default fidelity.

**Files:**
- Modify: `workers/cv-worker/src/structuring.py`
- Tests: `workers/cv-worker/tests/test_structuring.py`

**Steps:**
1. Add an instruction classifier: `complete_faithful`, `explicit_short_version`, `explicit_rewrite`, `targeted_edit`.
2. Default is always `complete_faithful`.
3. Only `explicit_short_version` can condense; only `targeted_edit` can alter requested sections.
4. Add tests: “CV standard” remains faithful; “raccourcis à 2 pages” allows condensation but still blocks hallucination.

**Done when:** The system supports requested edits but never treats vague instructions as permission to rewrite.

---

## Phase 2 — Human-level layout engine

### Task 2.1: Create deterministic page metrics report

**Objective:** Give the worker a reusable report that scores visual quality per page.

**Files:**
- Modify/Create: `workers/cv-worker/src/layout_intelligence.py`
- Modify: `workers/cv-worker/src/qa.py`
- Tests: `workers/cv-worker/tests/test_layout_intelligence.py`, `tests/test_qa_layout.py`

**Metrics:**
- page character count;
- used height ratio;
- bottom blank space;
- starts with continuation;
- has orphan heading;
- has experience title near page bottom;
- section split quality;
- final page density;
- page balance delta vs previous/next.

**Done when:** Every rendered PDF produces a concise machine-readable layout report.

### Task 2.2: Generate multiple safe layout variants

**Objective:** Stop relying on one render + one retry. Generate safe variants and choose best.

**Files:**
- Modify: `workers/cv-worker/src/main.py`
- Modify: `workers/cv-worker/src/layout_intelligence.py`
- Modify: `workers/cv-worker/src/rendering.py`
- Tests: `workers/cv-worker/tests/test_layout_intelligence_smoke.py`

**Variants:**
- default grouped;
- anti-crowding;
- grouped experiences with smarter page breaks;
- compact-but-readable spacing;
- continuation-safe mode;
- skills-balanced mode.

**Rules:**
- Never mutate source content.
- Never remove bullets to improve layout.
- Never force every experience onto its own page if grouping is readable.
- Prefer fewer pages only if readability remains good.

**Done when:** The worker can render 2–4 variants and select the best by score.

### Task 2.3: Implement layout scoring

**Objective:** Pick the variant closest to what a communication person would choose.

**Scoring priorities:**
Hard fail:
- contact leak;
- text overflow;
- bad glyphs;
- missing logo/watermark;
- source fidelity issue.

Soft score penalties:
- page too dense;
- page too sparse;
- last page with tiny tail;
- title at bottom of page;
- continuation page starts with one short leftover section;
- huge imbalance between pages;
- skills block too dense;
- first page too empty.

**Done when:** Oussama-like, Zahia-like and Gaël-like CVs choose better pagination without manual intervention.

### Task 2.4: Build real regression fixtures

**Objective:** Lock the real CV issues into tests.

**Files:**
- Use sanitized fixtures in `workers/cv-worker/tests/fixtures/`
- Tests: `test_layout_intelligence_smoke.py`, `test_structuring.py`, `test_qa_layout.py`

**Fixtures:**
- Oussama-like medium dense CV;
- Zahia-like long AMOA/assurance CV;
- Gaël-like LinkedIn export with page markers;
- THOREZ-like source with achievements/tools sections;
- one sparse CV with few experiences.

**Done when:** Future changes cannot regress the known layout/fidelity failures.

---

## Phase 3 — Preview and simple correction loop

### Task 3.1: Improve request detail page for `draft_ready`

**Objective:** Make draft state understandable for non-technical W hub users.

**Files:**
- Modify: `apps/web/app/requests/[id]/page.tsx`
- Modify: `apps/web/lib/request-detail-ui.ts`
- Tests: `apps/web/tests/request-detail-ui.test.ts`, `request-detail-page.test.ts`

**UI copy:**
- `Brouillon généré — contenu sécurisé, mise en page à vérifier`.
- Show only human-readable warnings: “page 3 trop dense”, “dernière page un peu vide”, “saut de page à vérifier”.
- Hide internal QA codes by default.

**Done when:** A colleague can understand whether they can use the PDF or ask a correction.

### Task 3.2: Add correction request presets

**Objective:** Let users request layout corrections without writing technical prompts.

**Files:**
- Modify: `apps/web/app/requests/[id]/page.tsx`
- Modify: `apps/web/app/requests/[id]/actions.ts`
- Worker already consumes unresolved comments.

**Presets:**
- `Aérer la mise en page`;
- `Réduire les gros blancs`;
- `Éviter les titres en bas de page`;
- `Rééquilibrer les expériences`;
- `Conserver le contenu mais améliorer les sauts de page`.

**Done when:** User can click a correction, relaunch, and the worker receives clear layout-only instructions.

### Task 3.3: Add PDF preview thumbnails

**Objective:** Reduce blind downloads and make visual review fast.

**Options:**
- Minimal first version: browser opens/downloads PDF only.
- Better version: generate page PNG thumbnails as worker artifacts using PyMuPDF and show them in request detail.

**Files:**
- Modify: `workers/cv-worker/src/storage.py`
- Modify: `workers/cv-worker/src/qa.py` or new `preview.py`
- Modify: `apps/web/app/requests/[id]/page.tsx`

**Done when:** User sees page previews without opening the PDF locally.

---

## Phase 4 — Stabilize renderer, assets and deployment

### Task 4.1: Move renderer into repo or package it explicitly

**Objective:** Remove dependency on `/root/.hermes/scripts/whub_cv_renderer.py` as a hidden production file.

**Files:**
- Create: `workers/cv-worker/src/renderer/whub_cv_renderer.py` or `workers/cv-worker/renderer/whub_cv_renderer.py`
- Modify: `workers/cv-worker/src/config.py`
- Modify: `workers/cv-worker/src/rendering.py`
- Tests: renderer overflow tests.

**Done when:** A fresh checkout contains the renderer used by production.

### Task 4.2: Version W hub assets and fonts

**Objective:** Prevent missing logo/watermark/font incidents.

**Files:**
- Add: `workers/cv-worker/assets/whub/logo.png`
- Add: `workers/cv-worker/assets/whub/watermark.png`
- Add or document fonts path.
- Modify: asset preflight script and settings.

**Rules:**
- Use validated embedded W hub CV assets, not public website assets.
- Keep dimension checks: logo `1051×398`, watermark `1192×1192`.

**Done when:** Renderer tests do not depend on `/root/.hermes/image_cache`.

### Task 4.3: Add worker startup preflight

**Objective:** Fail fast if assets/renderer/fonts are missing before a user submits a CV.

**Files:**
- Modify: `workers/cv-worker/src/main.py`
- Modify: `workers/cv-worker/src/rendering.py`

**Steps:**
1. On worker startup, check renderer path, assets, fonts and Supabase config.
2. Log a clear error and stop if missing.
3. Add systemd restart behavior already present.

**Done when:** Missing assets are detected at startup, not after a CV fails.

---

## Phase 5 — Ultra-simple internal UX

### Task 5.1: Simplify `/requests/new`

**Objective:** Make the portal understandable in 10 seconds.

**Fields:**
- Upload CV PDF.
- Prénom candidat.
- Titre court optionnel.
- Consignes optionnelles.
- Default checkbox/label: `Mode fidèle : mise en page uniquement`.

**Remove/avoid:**
- technical language;
- too many choices;
- QA vocabulary;
- anything that suggests automatic rewrite.

**Done when:** A W hub user knows exactly what to do without explanation.

### Task 5.2: Dashboard focused on action

**Objective:** Show only useful states.

**Statuses:**
- `En attente`;
- `Génération en cours`;
- `Prêt`;
- `Brouillon à vérifier`;
- `Bloqué — contenu/coordonnées à contrôler`;
- `Échec technique`.

**Done when:** Users know whether to download, correct, retry or ask Clément/admin.

### Task 5.3: Add admin-only diagnostics

**Objective:** Keep the UI simple while preserving debug visibility for Clément.

**Admin view:**
- raw QA report;
- worker events;
- last error;
- retry/reset button;
- PDF/JSON artifact links.

**Done when:** Normal users see simple UI; Clément can debug without Supabase/manual SQL.

---

## Phase 6 — Release gates and smoke tests

### Task 6.1: Add one command for all gates

**Objective:** Avoid manual scattered verification.

**Create:**
- `scripts/verify_all.sh` or package scripts.

**Commands:**
```bash
npm test
npm run build
cd workers/cv-worker && PYTHONPATH=. pytest -q
cd workers/cv-worker && python -m py_compile src/*.py
python /root/.hermes/skills/user-workflows/whub-client-cv-generator/scripts/verify_whub_assets.py
```

**Also fix:** Replace broken `next lint` script under Next 16.

**Done when:** Before every deploy/restart, one command proves the system is safe.

### Task 6.2: Add real E2E smoke path

**Objective:** Prove the portal works with a real CV, not only unit tests.

**Smoke:**
- upload fixture CV via Supabase/API or portal;
- wait for worker;
- download final PDF;
- verify no contact, first name only, source coverage, layout score, logo/watermark;
- save artifacts.

**Done when:** A release is not considered done without one successful real CV smoke.

---

## Suggested execution order

1. Phase 4 assets/renderer stabilization first, because missing local files can break everything.
2. Phase 1 fidelity strict finalization, because factual trust is non-negotiable.
3. Phase 2 layout variants/scoring, because this is the main product value.
4. Phase 3 preview/correction loop, because it reduces Clément babysitting.
5. Phase 5 UX simplification, because internal adoption depends on it.
6. Phase 6 release gates, or do it in parallel if moving fast.

## Success criteria

The next phase is successful when:
- a non-technical W hub user can upload a CV and generate a usable W hub PDF without Clément;
- default output contains no rewritten source content;
- no contact details/direct candidate links leak;
- at least 80–90% of normal CVs become `ready` without manual action;
- remaining safe-but-ugly CVs become `draft_ready` with simple correction options;
- worker can be restarted/rebuilt without manually restoring `/root/.hermes` assets;
- one command verifies worker + web + renderer before deploy.
