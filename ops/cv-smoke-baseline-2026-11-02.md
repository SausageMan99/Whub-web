# Baseline banc smoke CV Factory — 2026-11-02

Worker : `main` @ 9d86470 (phase 0 + phase 1), modèle google/gemini-2.5-flash via openrouter (Hermes v0.22.5, `--source tool`).

| Cas | Statut | Scores (layout/global/fidélité) | Δ vs 2026-09-21 |
|---|---|---|---|
| oussama | draft_ready | 100/82/82 | ✅ failed → draft_ready |
| zahia | ready | 100/100/100 | ⬆ draft_ready → ready |
| thorez | draft_ready | 88/82/82 | ⬇ ready → draft_ready (alertes fidélité douces) |
| dense | draft_ready | 88/88/100 | = |
| sanitize | ready | 100/100/100 | = |
| hodard | draft_ready | 88/82/82 | = |
| rayan | draft_ready | 88/82/82 | = |
| amina | draft_ready | 16/16/82 | ✅ failed → draft_ready, mais layout très faible |
| benjamin | draft_ready | 76/76/100 | ✅ failed → draft_ready (octets NUL OK) |
| noel | failed | — | = `structuring_invalid_json` (CV long) |
| yannick | failed | — | = `structuring_invalid_json` (CV long) |

**Réussis : 9/11 — 0 échec inattendu.**

## Notes
- oussama/thorez : la combinaison « QA passée + alertes fidélité douces » faisait planter `save_version`
  (classé à tort `transient_model_failure`). Corrigé en 9d86470 ; thorez aurait échoué sans ce correctif.
- noel/yannick : JSON invalide sur les CV longs découpés en blocs → phase 2 (sortie JSON contrainte par schéma).
- amina : passe désormais, mais layout 16/100 → à suivre pendant le comparatif de modèles (phase 3).
- Demande réelle Heidi (489cc766) récupérée en draft_ready.
