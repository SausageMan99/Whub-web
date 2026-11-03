# ops — bancs, décisions, comptes rendus

Documents datés, du plus récent au plus ancien. Chaque document dit ce qui a été mesuré, ce qui a été décidé et pourquoi. Le fonctionnement courant est décrit dans le [README principal](../README.md), et l'historique des versions dans [`CHANGELOG.md`](../CHANGELOG.md).

| Document | Contenu |
|---|---|
| [`cv-pagination-2026-11-03.md`](cv-pagination-2026-11-03.md) | Pagination : équilibrage des pages en caractères et en hauteur, ouverture d'expérience protégée, variante regroupée, faux positifs QA (débordement de compétences, prénom, taxonomie), décision « page dense acceptable seule = ready ». |
| [`cv-fidelity-qa-and-skills-2026-11-03.md`](cv-fidelity-qa-and-skills-2026-11-03.md) | Contrôle de couverture des expériences face aux mises en page PDF ; compétences lues d'après les styles du PDF (modèles Canva à deux colonnes). |
| [`model-bakeoff-2026-11-02.md`](model-bakeoff-2026-11-02.md) | Comparaison de 6 modèles sur 11 CV, choix de Gemini 2.5 Flash, nettoyeurs qui altéraient le texte, seuil d'appel unique à 40 000 caractères. |
| [`cv-smoke-baseline-2026-11-02.md`](cv-smoke-baseline-2026-11-02.md) | Banc après la remise en service : 9/11, 0 échec inattendu. |
| [`cv-smoke-baseline-2026-09-21.md`](cv-smoke-baseline-2026-09-21.md) | Banc de référence de septembre. |
| [`cv-smoke-worker-audit-2026-06-13.md`](cv-smoke-worker-audit-2026-06-13.md) | Audit du worker de juin. |
| `cv-quality-latest.md`, `cv-quality-history.jsonl` | Digest qualité. |

La panne du 16 au 30/10/2026 et la remise en service sont décrites dans [`.hermes/plans/2026-11-02_140000-remise-en-service-et-choix-modele.md`](../.hermes/plans/2026-11-02_140000-remise-en-service-et-choix-modele.md).

## Évolution du banc prod (11 CV)

| Date | Réussis | Ready | Remarque |
|---|---|---|---|
| 21/09/2026 | voir baseline | | référence |
| 02/11 | 9/11 | 2 | après remise en service ; noel et yannick en échec |
| 03/11 matin | 11/11 | 3 | backend OpenRouter, seuil 40 000, nettoyeurs corrigés |
| 03/11 midi | 11/11 | 6 | fausses alertes de couverture, compétences d'après les styles du PDF |
| 03/11 soir | 11/11 | 8 | pagination, faux positifs QA, alerte indicative |
