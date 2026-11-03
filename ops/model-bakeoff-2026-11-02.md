# Choix du modèle de structuration — 2026-11-02/03

**Décision (03/11) : `google/gemini-2.5-flash` reste le modèle principal, `anthropic/claude-haiku-5.5` en secours.**
CV traités en un seul appel jusqu'à 40 000 caractères (`WHUB_MEDIUM_CV_SINGLE_PASS_THRESHOLD=40000`).

Critère métier : le CV W hub doit être un copier-coller du CV source, remis en forme.
Les expériences ne doivent pas être reformulées, et tout le contenu d'origine doit s'y retrouver.

## Mesures

`workers/cv-worker/scripts/model_bakeoff.py`, hors prod, sur les 11 CV du banc :

- **couverture** : part des lignes de la source (≥ 30 caractères) retrouvées telles quelles dans le CV généré ;
- **copie exacte** : part des phrases d'expérience générées qui sont un extrait mot pour mot de la source.

### Tour 1 — découpage en blocs dès 10 000 caractères, 6 modèles

| Modèle | Échecs | Couverture | Copie exacte | Durée moy. | Coût 11 CV |
|---|---|---|---|---|---|
| anthropic/claude-haiku-5.5 | 1 | 0.829 | 1.0 | 26.5 s | $0.099 |
| openai/gpt-6-luna | 2 | 0.790 | 0.999 | 29.0 s | $0.046 |
| anthropic/claude-sonnet-5.5 | 2 | 0.785 | 1.0 | 23.1 s | $1.274 |
| google/gemini-3.8-flash | 2 | 0.773 | 1.0 | 40.2 s | $0.602 |
| mistralai/mistral-large-4-0 | 1 | 0.767 | 0.968 | 187.0 s | $0.913 |
| google/gemini-2.5-flash | 1 | 0.765 | 0.961 | 12.1 s | $0.146 |

Amina échouait pour **tous** les modèles : le découpage en blocs séparait une expérience de ses missions.
C'est le pipeline qui était en cause, pas le modèle.

### Tour 2 — un seul appel jusqu'à 40 000 caractères

| Modèle | Échecs | Couverture | Copie exacte | Durée moy. | Coût 11 CV |
|---|---|---|---|---|---|
| google/gemini-2.5-flash | 0 | **0.805** | 0.995 | **13.1 s** | $0.083 |
| anthropic/claude-haiku-5.5 (ZDR) | 0 | 0.759 | 1.0 | 33.4 s | $0.058 |

Haiku ne garde qu'un tiers du texte de thorez (0.333 contre 0.8).

### Tour 3 — Gemini 2.5 Flash après correction des nettoyeurs (03/11)

Les écarts de copie restants ne venaient pas du modèle : le nettoyage d'anonymisation altérait le texte.

- **Avant l'appel au modèle** (`source_sanitizer.py`) :
  - « ASP.NET », « ADO.NET » et « VB.NET » étaient pris pour des noms de domaine `.net` et supprimés ;
  - l'espace avant « : » et « ; » était retiré sur toutes les lignes.
- **Après l'appel** (`structuring.py`, `sanitize_contact_in_json` / `sanitize_identity_terms_in_json`) :
  - les mots « LinkedIn », « contact » et « email » étaient retirés de toutes les phrases (« campagnes LinkedIn Ads » → « campagnes Ads ») ;
  - la ponctuation était retouchée même sans coordonnée trouvée.
- Les ligatures PDF (« ﬁ », « ﬂ ») sont désormais converties en lettres normales à l'extraction.

Désormais, seules les lignes qui contiennent vraiment une coordonnée (email, téléphone, URL, profil) sont retouchées.

| Cas | Couverture avant → après | Copie exacte avant → après |
|---|---|---|
| yannick | 0.972 → 0.961 | 0.988 → 0.987 (0.799 sans le seuil 40k) |
| benjamin | 0.679 → 0.714 | 0.958 → 1.0 |
| hodard | 0.84 → 0.84 | 1.0 → 1.0 |
| zahia | 0.812 → 0.814 | 1.0 → 1.0 |

Il reste deux micro-écarts du modèle sur yannick : un trait d'union ajouté, et une faute de frappe du CV corrigée.

Effet de bord corrigé dans la foulée (`skills_intelligence.py`) : la section « Compétences » s'arrêtait par accident
sur la compétence « Formation des utilisateurs finaux » une fois sa puce retirée. Une fois la puce conservée, elle ne
s'arrêtait plus du tout : les titres en lettres espacées (« E X P É R I E N C E S ») n'étaient pas reconnus.
Zahia : 189 → 68 compétences, 6 → 4 pages, ready.

## Banc prod — 03/11 (worker redémarré, Gemini 2.5 Flash + secours Haiku, seuil 40k)

| Cas | Statut | Layout/global/fidélité | Pages | Durée (s) |
|---|---|---|---|---|
| oussama | draft_ready | 88/82/82 | 2 | 8.1 |
| zahia | **ready** | 100/100/100 | 4 | 15.6 |
| thorez | **ready** | 100/100/100 | 1 | 3.6 |
| dense | draft_ready | 88/88/100 | 2 | 5.5 |
| sanitize | **ready** | 100/100/100 | 1 | 4.1 |
| hodard | draft_ready | 88/82/82 | 2 | 6.8 |
| rayan | draft_ready | 88/82/82 | 2 | 8.1 |
| amina | draft_ready | 64/64/100 | 6 | 21.7 |
| benjamin | draft_ready | 88/88/100 | 2 | 15.8 |
| noel | draft_ready | 52/52/100 | 15 | 32.9 |
| yannick | draft_ready | 88/82/82 | 10 | 31.8 |

**11/11 réussis, 3 ready** (02/11 : 9/11, 2 ready ; noel et yannick échouaient).

Les alertes de fidélité restantes d'oussama et hodard sont des faux positifs du contrôle QA, pas du contenu perdu :

- **oussama** : la ligne source « 07/2022 – 01/2024 Software Engineer - CDI chez BNP Paribas - France » est attendue d'un seul tenant, alors que le CV la répartit en date / poste / entreprise ;
- **hodard** : des fragments de la colonne latérale du PDF sont mêlés aux missions.

Ces alertes font passer les CV en draft_ready (relecture humaine) : c'est le côté prudent, mais à affiner.

## Pourquoi Gemini 2.5 Flash

- Meilleure couverture en un seul appel, et 2,5 fois plus rapide que Haiku.
- Copie exacte à 0.99–1.0 une fois les nettoyeurs corrigés.
- Le secours Haiku 5.5 (copie exacte 1.0 sur les deux tours) prend le relais automatiquement via OpenRouter si Gemini est indisponible.

## Point données

`data_collection=deny` est toujours envoyé : OpenRouter n'utilise que des fournisseurs qui n'entraînent pas leurs modèles sur les données.
Aucun fournisseur de Gemini 2.5 Flash ne propose la non-conservation (ZDR, *zero data retention*).
`WHUB_LLM_ZERO_DATA_RETENTION` reste donc à `false` ; passé à `true`, il ferait refuser toutes les requêtes Gemini.
