# D0 — `draft_ready` pour PDF brouillon avec warnings layout

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Modifier W hub CV Factory pour livrer un PDF téléchargeable en statut `draft_ready` quand la QA ne remonte que des défauts subjectifs de layout, tout en gardant les garde-fous sécurité/fidélité strictement bloquants.

**Architecture:** Séparer explicitement la QA en deux familles: hard blockers et soft layout warnings. Le worker doit toujours uploader une version PDF + QA report quand le PDF est sûr mais imparfait, puis marquer la demande `draft_ready`; il doit continuer à marquer `qa_failed`/`failed` pour tout risque contact, identité, fidélité, PDF corrompu, overflow ou sécurité. Le web doit afficher `draft_ready` comme un état téléchargeable mais non validé, avec warnings visibles et possibilité de retry/révision.

**Tech Stack:** Python worker Supabase + PyMuPDF/ReportLab, Supabase SQL migrations, Next.js/React portal, Node/Python tests.

---

## Décision produit figée

`ready` = PDF final validé, QA sans hard blocker et sans soft warning.

`draft_ready` = PDF généré, téléchargeable, contact/fidélité/sécurité OK, mais warnings layout subjectifs présents. Ce n’est pas un échec technique et l’utilisateur peut l’exploiter comme brouillon.

`qa_failed` = PDF généré ou tentative de PDF non acceptable car au moins un hard blocker QA existe.

`failed` = erreur d’exécution hors QA: extraction impossible, structuration impossible, upload impossible, exception worker, PDF non généré, etc.

## Mapping exact hard vs soft

### Hard blockers — restent bloquants

Ces signaux doivent empêcher toute livraison client et mener à `qa_failed` si le pipeline a atteint la QA, ou `failed` si l’étape technique n’a pas produit de PDF exploitable.

Dans `workers/cv-worker/src/qa.py`:

- `contact_hits` non vide: email, téléphone, LinkedIn, URL, GitHub, domaine `.com`, ou `forbidden_name:<nom>`.
- `bad_glyphs == true`: glyphes corrompus ou `\x00`.
- `content_integrity_issues` non vide, notamment:
  - `json_fact_missing_from_pdf`;
  - `source_experience_location_missing_from_pdf`;
  - `pdf_fact_absent_from_source`;
  - répétitions placeholders numérotées.
- `text_overflow_hits` non vide: texte hors zone lisible/marge.
- `has_logo == false` ou `has_watermark == false`.
- `pages <= 0` ou PDF illisible/corrompu à l’ouverture PyMuPDF.

Hors `qa.py`, restent hard aussi:

- contact dans le JSON structuré via `assert_no_contact_in_json(structured)`;
- nom complet non normalisé quand `candidate_first_name` contient prénom + nom;
- mauvais utilisateur/RLS, accès signé non scoped, fuite secret;
- hallucination/altération factuelle détectée avant ou pendant QA;
- exception de download/source/storage/worker.

### Soft layout warnings — non bloquants si seuls

Ces codes peuvent produire `draft_ready` seulement si tous les hard blockers ci-dessus sont absents:

- `page_too_dense`
- `last_page_sparse`
- `bad_page_break`
- `skill_block_too_long`
- `skills_too_dense`
- `experience_orphan_heading`
- `experience_section_orphan_heading`
- `skill_overflow_page_created`

Important: `experience_section_orphan_heading` existe déjà dans `qa.py` ligne ~193 même s’il n’était pas listé dans le brief initial; il est de même nature que `experience_orphan_heading` et doit être soft.

## Supabase: migration nécessaire

Le schéma actuel bloque `draft_ready`:

- `supabase/migrations/001_init.sql` limite `cv_requests.status` à `submitted, processing, qa_failed, ready, revision_requested, failed, cancelled, archived`.
- `cv_versions.qa_status` est limité à `pending, passed, failed`.

Créer une migration nouvelle, par exemple:

`supabase/migrations/005_draft_ready_status.sql`

Contenu attendu, à adapter au nom réel des contraintes si Supabase les a auto-nommées différemment en prod:

```sql
alter table public.cv_requests
  drop constraint if exists cv_requests_status_check;

alter table public.cv_requests
  add constraint cv_requests_status_check
  check (status in (
    'submitted',
    'processing',
    'qa_failed',
    'ready',
    'draft_ready',
    'revision_requested',
    'failed',
    'cancelled',
    'archived'
  ));

alter table public.cv_versions
  drop constraint if exists cv_versions_qa_status_check;

alter table public.cv_versions
  add constraint cv_versions_qa_status_check
  check (qa_status in ('pending', 'passed', 'draft', 'failed'));
```

Ne pas modifier `004_claim_rpc.sql`: le worker doit continuer à ne claim que `submitted` et `revision_requested`. `draft_ready` n’est pas une file active; il devient retryable via action utilisateur.

## Worker: design cible

### Task 1: classifier la QA sans affaiblir `run_qa`

**Objective:** Ajouter une fonction pure qui décide `passed | draft | failed` à partir du report QA.

**Files:**
- Modify: `workers/cv-worker/src/qa.py`
- Test: `workers/cv-worker/tests/test_qa.py` ou nouveau `workers/cv-worker/tests/test_qa_classification.py`

**Implementation attendu:**

Ajouter des constantes explicites:

```python
SOFT_LAYOUT_CODES = {
    "page_too_dense",
    "last_page_sparse",
    "bad_page_break",
    "skill_block_too_long",
    "skills_too_dense",
    "experience_orphan_heading",
    "experience_section_orphan_heading",
    "skill_overflow_page_created",
}

HARD_QA_FIELDS = (
    "contact_hits",
    "content_integrity_issues",
    "text_overflow_hits",
)
```

Ajouter:

```python
def classify_qa_report(report: dict) -> tuple[str, list[dict]]:
    """Return ('passed'|'draft'|'failed', layout warnings to expose)."""
    hard_failed = (
        bool(report.get("contact_hits"))
        or bool(report.get("bad_glyphs"))
        or bool(report.get("content_integrity_issues"))
        or bool(report.get("text_overflow_hits"))
        or not report.get("has_logo")
        or not report.get("has_watermark")
        or int(report.get("pages") or 0) <= 0
    )
    if hard_failed:
        return "failed", []

    layout_issues = report.get("layout_issues") or []
    unknown_layout = [issue for issue in layout_issues if issue.get("code") not in SOFT_LAYOUT_CODES]
    if unknown_layout:
        return "failed", []
    if layout_issues:
        return "draft", layout_issues
    return "passed", []
```

Garder `run_qa()` strict et compatible: il peut continuer à lever `QAError` quand `passed` est false. L’assouplissement doit être dans le worker via classification du report, pas en supprimant les checks.

**Tests à écrire:**

- `contact_hits=['email']` + `layout_issues=[page_too_dense]` => `failed`.
- `text_overflow_hits` non vide + soft layout => `failed`.
- `content_integrity_issues` non vide => `failed`.
- `bad_glyphs=true` => `failed`.
- `has_logo=false` ou `has_watermark=false` => `failed`.
- `layout_issues=[{'code':'page_too_dense'}]` et hard fields vides => `draft` avec warnings.
- plusieurs soft codes ensemble => `draft`.
- aucun problème => `passed`.
- code layout inconnu => `failed` par défaut conservateur.

### Task 2: sauvegarder les versions draft

**Objective:** Permettre au worker d’uploader input/PDF/QA report pour `draft_ready` sans mentir sur `qa_status`.

**Files:**
- Modify: `workers/cv-worker/src/storage.py`
- Test: `workers/cv-worker/tests/test_storage.py` si présent, sinon test mocké du payload dans un nouveau fichier.

**Implementation attendu:**

Remplacer `save_success(...)` par une fonction plus générique ou ajouter un paramètre:

```python
def save_version(
    request_id: str,
    version_number: int,
    structured_json: dict,
    pdf_path: Path,
    qa_report: dict,
    *,
    request_status: str = "ready",
    qa_status: str = "passed",
) -> str:
```

Contraintes:

- `request_status` autorisé: `ready` ou `draft_ready` seulement.
- `qa_status` autorisé: `passed` ou `draft` seulement.
- `cv_versions.qa_report` conserve le report complet, y compris `layout_issues`.
- `cv_requests.current_version_id` doit être renseigné aussi pour `draft_ready`.
- `ready_at` peut être renseigné pour `draft_ready` aussi, car c’est le timestamp de disponibilité du PDF. Si l’équipe veut une sémantique plus propre plus tard, ajouter `draft_ready_at`; pas nécessaire pour D0.

Garder `save_success = save_version` ou un wrapper pour limiter le diff.

### Task 3: modifier `process_job` pour accepter les soft failures

**Objective:** Quand `run_qa` lève `QAError`, sauver quand même le PDF si classification = `draft`.

**Files:**
- Modify: `workers/cv-worker/src/main.py`
- Modify: `workers/cv-worker/src/layout_retry.py` si sa logique reste limitée à `page_too_dense`
- Test: `workers/cv-worker/tests/test_main_layout_retry.py` ou nouveau `workers/cv-worker/tests/test_main_draft_ready.py`

**Flow cible:**

1. Render initial.
2. Run QA.
3. Si QA passed => `save_version(..., request_status='ready', qa_status='passed')`, event `ready`.
4. Si QAError:
   - classifier `e.report`.
   - si `failed` => logique actuelle: éventuellement layout retry si safe, sinon `qa_failed`.
   - si `draft` => optionnellement faire une correction déterministe existante si applicable, mais ne pas bloquer si la correction échoue uniquement sur soft layout.
5. Après retry layout:
   - si QA passed => `ready`.
   - si QAError classée `draft` => `draft_ready`.
   - si QAError classée `failed` => `qa_failed`.

Décision simple D0: conserver le retry existant pour `page_too_dense`, mais élargir `is_safe_layout_retry_report()` à tous les soft layout codes ou créer `is_soft_layout_only_report(report)` dans `qa.py`. Ne retry qu’une fois. Ne pas créer de boucle.

Événements à émettre:

```python
emit_event(request_id, "draft_ready", {
    "version_id": version_id,
    "version_number": version_number,
    "layout_warnings": qa_report.get("layout_issues", []),
})
```

Pour `ready`, garder l’event existant.

### Task 4: garder le retry utilisateur possible

**Objective:** Autoriser une demande `draft_ready` à repartir en `revision_requested` si Clément veut une version nickel.

**Files:**
- Modify: `apps/web/app/requests/[id]/actions.ts`
- Modify tests: `apps/web/tests/retry-request.test.ts`

Changements:

- Inclure `draft_ready` dans les statuts retryables côté action serveur.
- La mise à jour `.in('status', [...])` doit accepter `draft_ready`.
- Le payload event peut devenir `previous_status: request.status` au lieu de `failed_or_qa_failed`.

Ne pas rendre `ready` retryable sauf si déjà voulu par le produit. Ici, le brouillon avec warnings doit pouvoir être retravaillé; le final prêt reste stable.

## UI: stratégie minimale D0

### Task 5: statut et barre de progression

**Files:**
- Modify: `apps/web/lib/cv-ui.ts`
- Modify: `apps/web/components/StatusBadge.tsx`
- Modify: `apps/web/components/CvProgressBar.tsx`
- Tests: `apps/web/tests/cv-ui.test.ts`

Comportement:

- `draft_ready` doit être à 100%, pas 85%, car le PDF est disponible.
- Label recommandé: `Brouillon prêt`.
- Helper recommandé: `PDF téléchargeable, avec alertes de mise en page à relire avant envoi client.`
- Badge recommandé: orange/amber, texte `Brouillon QA` ou `Brouillon prêt`.
- Progress bar: couleur amber/orange, pas rouge.

### Task 6: page détail demande

**Files:**
- Modify: `apps/web/app/requests/[id]/page.tsx`

Comportement:

- Afficher le bouton download si `current_version_id`/`final_pdf_path` existe, y compris en `draft_ready`.
- Afficher un encart warnings quand `request.status === 'draft_ready'` ou quand la dernière version a `qa_status === 'draft'`:
  - titre: `PDF brouillon disponible`;
  - texte: `Les contrôles sécurité/fidélité sont passés. Les alertes restantes concernent la lisibilité ou la mise en page.`;
  - lister les `qa_report.layout_issues[].message` ou au minimum les `code` + `page`.
- Garder le bouton de retry/révision visible pour `draft_ready`.
- Ne pas afficher `draft_ready` comme une erreur bloquante.

### Task 7: dashboard

**Files:**
- Modify: `apps/web/app/dashboard/page.tsx`

Comportement:

- Ajouter un compteur `Brouillons` ou inclure séparément les `draft_ready`.
- Ne pas les compter dans `Prêts` si la métrique `Prêts` signifie `Validés côté QA`.
- Ne pas les compter dans `Erreurs`.

## Tests minimum avant review

Worker:

```bash
cd /root/whub-cv-factory/workers/cv-worker
python -m pytest tests/test_qa.py tests/test_qa_layout.py tests/test_main_layout_retry.py -q
python -m py_compile src/main.py src/qa.py src/storage.py src/layout_retry.py
```

Web:

```bash
cd /root/whub-cv-factory/apps/web
npm test -- --runInBand
npm run build
```

Repo smoke utile si disponible:

```bash
python ~/.hermes/skills/user-workflows/whub-client-cv-generator/scripts/verify_whub_assets.py
```

## Non-objectifs D0

- Pas de déploiement prod.
- Pas de restart worker.
- Pas d’abaissement de seuils QA.
- Pas de suppression de `run_qa` strict.
- Pas de changement RLS/storage policy sauf si une implémentation découvre que les downloads de version `draft_ready` sont bloqués par une règle existante. A priori, `current_version_id` + `cv_versions` existants suffisent.
- Pas d’auto-envoi client: `draft_ready` est exploitable par W hub, pas validé client-facing final.

## Critères d’acceptation

- Une QA contenant seulement `page_too_dense` ou `skills_too_dense` produit un `cv_versions` avec `qa_status='draft'`, un PDF uploadé, un `qa_report` complet, `cv_requests.status='draft_ready'`, `current_version_id` renseigné, event `draft_ready`.
- Une QA contenant `contact_hits`, `forbidden_name`, `text_overflow_hits`, `bad_glyphs`, `content_integrity_issues`, logo/watermark absent ou PDF vide reste `qa_failed` sans PDF présenté comme exploitable.
- Le portail permet de télécharger un brouillon, affiche clairement les warnings, et permet de relancer une révision depuis `draft_ready`.
- Les tests couvrent le mélange hard+soft: hard gagne toujours.
- Aucun secret ou donnée candidat sensible n’est ajouté aux logs/handoffs.
