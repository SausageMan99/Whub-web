# Baseline banc smoke CV Factory — 2026-09-21

Worker : code du working tree (commit 38eb786 + fichiers non commités), modèle google/gemini-2.5-flash via openrouter.

| Cas | Statut | Attendu (avant fix) | Durée (s) | Version | QA | Scores (layout/global/fidélité) | Alertes douces | Verdict |
|---|---|---|---|---|---|---|---|---|
| oussama | failed | pass | 190 | — | — | — | 0 | ⚠️ INATTENDU |
| zahia | draft_ready | pass | 43 | 111 | draft | 88/88/100 | 1 | ✅ attendu |
| thorez | ready | pass | 95 | 112 | passed | 100/100/100 | 0 | ✅ attendu |
| dense | draft_ready | pass | 38 | 113 | draft | 88/88/100 | 1 | ✅ attendu |
| sanitize | ready | pass | 95 | 114 | passed | 100/100/100 | 0 | ✅ attendu |
| hodard | draft_ready | pass | 32 | 115 | draft | 88/82/82 | 4 | ✅ attendu |
| rayan | draft_ready | pass | 236 | 116 | draft | 88/82/82 | 2 | ✅ attendu |
| amina | failed | pass | 319 | — | — | — | 0 | ⚠️ INATTENDU |
| benjamin | failed | fail | 6 | — | — | — | 0 | ✅ attendu |
| noel | processing | fail | 1502 | — | — | — | 0 | ✅ attendu |
| yannick | failed | fail | 294 | — | — | — | 0 | ✅ attendu |

**Réussis : 6 — Échoués : 5 — Cas enregistrés : 11/11**

Écarts par rapport aux attentes pré-correctif :
- oussama: failed (attendu pass)
- amina: failed (attendu pass)

## Suivi post-banc

- `noel` : le banc a plafonné à 1500 s ; le worker a terminé ensuite — échec réel à 15:26:36 en `structuring_invalid_json` (structuration jusqu'au bloc 27/29, ~27 min au total). Demande conservée (8ac53695, failed) car le cleanup est maintenant sauté pour les statuts non terminaux.
- `yannick` : échec en `structuring_invalid_json` après 9 blocs (294 s) — catégorie honnête.
- `benjamin` : échec en 6 s, encore classé `transient_model_failure` alors que la cause est les octets NUL du PDF (embedded null byte). Repro conservée : 40b50223.
- `oussama` : intermittent — avait réussi (draft_ready, v108) au premier passage du jour puis échoué ; structuration OK en 14,6 s puis sortie modèle inexploitable, classée `transient_model_failure`, sans retry.
- `amina` : structuration complète (6/6 blocs) puis refus du gate fidélité (`source_fidelity`) — à investiguer en étape 1.
- Incident worker 14:42 UTC : suppression en vol d'une demande (smoke tué) → FK violation à la sauvegarde → `fail_job` non protégé → crash process ; systemd a redémarré (NRestarts=1). Le script smoke est durci : cleanup uniquement pour les statuts terminaux.
- Note : les logs worker sont bien dans journald (utile pour l'étape 1).
