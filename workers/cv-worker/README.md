# W hub CV Worker

Worker Python qui récupère les demandes CV dans Supabase, transforme le PDF candidat en CV W hub et enregistre la version, son PDF et son rapport qualité.

Le fonctionnement complet (pipeline, statuts, base, variables) est décrit dans le [README principal](../../README.md). Cette page sert de carte du code pour travailler sur le worker.

## Lancer

En production, le worker tourne en service systemd `whub-cv-worker` :

- dossier de travail : ce dossier ;
- variables : `/root/whub-cv-factory/.env` ;
- commande : `.venv/bin/python -m src.main`.

```bash
systemctl restart whub-cv-worker
```

```bash
journalctl -u whub-cv-worker -n 100 --no-pager
```

Le worker lit le code au démarrage : après une modification, il faut le redémarrer.

## Carte du code (`src/`)

| Module | Rôle |
|---|---|
| `main.py` | boucle de polling, `process_job` (étapes, timings, événements, décision ready / draft_ready) |
| `extraction.py` | texte PDF dans l'ordre visuel, OCR Tesseract de secours, normalisations (contrôles, ligatures, puces Wingdings et « o ») |
| `text_readability.py` | score de lisibilité qui déclenche l'OCR (`READABILITY_OCR_THRESHOLD = 0.5`) |
| `source_sanitizer.py` | retrait des coordonnées et des lignes ATS ; ne touche pas une ligne sans coordonnée ; garde les noms `.NET` |
| `quality_report.py` | profil source, rapport qualité anonymisé, `should_require_human_review` |
| `structuring.py` | prompt, un appel ou des blocs, assemblage, nettoyage du JSON, contrôle de fidélité et de couverture, classement des erreurs, taxonomie `WHUB_SKILL_CATEGORY_TAXONOMY` |
| `llm_backend.py` | appel OpenRouter : schéma JSON strict, secours, relances, journal des coûts |
| `visual_skills_extraction.py` | compétences lues dans le PDF source (titres connus, ou styles des modèles Canva) |
| `skills_intelligence.py` | parseur de compétences de secours, dédoublonnage, taxonomie |
| `layout/` | `run_layout` : variantes `base` / `layout_retry` / `grouped` et sélection |
| `rendering.py` | lance le renderer en sous-processus |
| `qa.py` | QA du PDF : sécurité, intégrité, mise en page, score de goût humain, `classify_qa_report` |
| `storage.py` | `save_version` et ses garde-fous de statut |
| `config.py` | paramètres (voir les variables dans le README principal) |

Le renderer `renderer/whub_cv_renderer.py` est un script autonome. Il ne peut pas importer `src/`, donc ses seuils qui reflètent la QA sont recopiés avec un commentaire, par exemple `QA_DENSE_PAGE_CHARS = 3000` pour `qa.PAGE_DENSE_CHAR_THRESHOLD`.

## Principes à respecter

1. **Copier, ne pas réécrire.** Le CV W hub est un copier-coller du CV source, remis en forme. Tout nettoyage automatique ne touche que ce qu'il doit retirer (une coordonnée, un nom), et laisse le reste au caractère près.
2. **Dans le doute, garder ou relire.** Un remplacement automatique (compétences lues dans le PDF, découpage) n'est appliqué que s'il est fiable ; sinon on garde l'existant, ou on envoie en `draft_ready` pour relecture.
3. **Une alerte doit être vraie.** Un faux positif fait perdre la confiance dans les brouillons. Corriger le contrôle, en gardant un test qui prouve qu'un vrai problème reste détecté.
4. **La mise en page ne change jamais le contenu** (`assert_layout_retry_preserves_content`).

## Tests

```bash
../../.venv/bin/python -m pytest -q
```

Tests ajoutés les 02 et 03/11/2026, par sujet :

| Fichier | Sujet |
|---|---|
| `tests/test_llm_backend.py` | schéma, fournisseurs, secours, relances, erreurs OpenRouter |
| `tests/test_extraction_ocr.py` | lisibilité, OCR, ligatures, puces Wingdings et « o » |
| `tests/test_source_sanitizer.py` | noms `.NET`, lignes sans coordonnée gardées telles quelles |
| `tests/test_output_sanitizers_keep_clean_text.py` | JSON : seules les chaînes avec coordonnée ou nom sont retouchées |
| `tests/test_structuring_block_assembly.py` | langues, certifications et expériences coupées dans les CV longs |
| `tests/test_experience_coverage_layouts.py` | contrôle de couverture face aux mises en page PDF (une mission supprimée reste signalée) |
| `tests/test_visual_skills_styled_sections.py` | compétences d'après les styles du PDF et leurs garde-fous |
| `tests/test_layout_pagination_balance.py` | règles QA de débordement, prénom et taxonomie, choix des variantes, alerte indicative |
| `tests/test_renderer_overflow.py` | ouverture d'expérience, anti-crowding |
| `tests/test_cv_health_alert.py` | règles des alertes de santé |

Les tests qui lisent les PDF de `cv_test_bank/` (ignorés par git) sont sautés si ces fichiers manquent.

## Mesurer avant de changer

La sortie du modèle varie d'un appel à l'autre : un seul essai ne prouve rien. Pour un changement de modèle, de prompt, de nettoyage ou de contrôle :

```bash
set -a && . ../../.env && set +a
../../.venv/bin/python scripts/model_bakeoff.py run --model google/gemini-2.5-flash --out /tmp/bakeoff/avant.jsonl
```

```bash
../../.venv/bin/python scripts/model_bakeoff.py report /tmp/bakeoff/avant.jsonl /tmp/bakeoff/apres.jsonl
```

Pour un changement de mise en page, refaire le rendu des **mêmes** `structured.json` (produits par le bake-off dans le dossier de sortie) avant et après, avec `run_layout`. Enfin, valider en prod avec `python3 scripts/cv_smoke_battery.py --reset`, depuis la racine du dépôt.

## Décisions et comptes rendus

- [`ops/model-bakeoff-2026-11-02.md`](../../ops/model-bakeoff-2026-11-02.md) : choix du modèle, nettoyeurs corrigés.
- [`ops/cv-fidelity-qa-and-skills-2026-11-03.md`](../../ops/cv-fidelity-qa-and-skills-2026-11-03.md) : contrôle de couverture, compétences d'après les styles du PDF.
- [`ops/cv-pagination-2026-11-03.md`](../../ops/cv-pagination-2026-11-03.md) : pagination, faux positifs QA, alerte indicative.
