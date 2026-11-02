# CV Factory — remise en service + choix du modèle (2026-11-02)

## Diagnostic (vérifié le 02/11)

- **100 % des demandes échouent depuis au moins le 16/10** (110 échecs `model_nonzero_exit` dans journald, aucun succès depuis).
- Cause racine reproduite : la version actuelle de Hermes (v0.22.5, build du 22/10) refuse
  `--source whub-cv-worker` → `Hermes couldn't start the model connection: invalid_params`.
  Le modèle n'est jamais appelé (échec en ~3 s).
- `--source tool` (valeur prévue par Hermes pour les intégrations tierces) fonctionne avec la commande complète du worker.
- Problème de fond : le worker dépend d'un CLI interactif (Hermes) qui change à chaque mise à jour automatique,
  et il parse du texte libre en JSON — d'où aussi les `structuring_invalid_json` sur les CV longs (noel, yannick).
- Les retries (3 tentatives) masquent l'erreur : `last_error` ne contient pas le stderr réel de Hermes.

## Phase 0 — Remettre en marche (≈ 30 min)

1. `structuring.py::_default_hermes_runner` : `--source whub-cv-worker` → `--source tool`.
2. Test unitaire qui fige l'argv attendu.
3. Classer `invalid_params` / « couldn't start the model connection » en `model_config_error`
   **non retryable**, et inclure le stderr (sans données CV) dans `last_error`.
4. Commit, push (avec les 2 commits non poussés), restart `whub-cv-worker`.
5. Rejouer 1 CV réel → `draft_ready`/`ready` attendu. Relancer les demandes échouées depuis le 16/10.

## Phase 1 — Corriger les échecs connus du banc (≈ 1 j)

| Cas | Problème | Action |
|---|---|---|
| benjamin | octets NUL classés `transient_model_failure` | vérifier que `_sanitize_prompt_for_subprocess` + bucket `pre_model_subprocess_error` couvrent le cas ; test sur la repro 40b50223 |
| oussama | sortie modèle inexploitable, intermittent, pas de retry | retry ciblé sur JSON invalide (1 retry, prompt de réparation) |
| noel / yannick | `structuring_invalid_json` sur CV longs, jusqu'à 27 min | résolu à la racine par la phase 2 (sortie JSON contrainte) ; en attendant, plafond de durée par job |
| amina | refus `source_fidelity` après structuration complète | analyser le rapport de couverture : vrai trou de contenu ou faux positif du gate |

Puis : commiter/trier les modifs non commitées (web CSS, `revisions.py`) et rejouer le banc des 11 cas.
**Critère de sortie : 9/11 au minimum, 0 échec inattendu.**

## Phase 2 — Fiabiliser l'appel modèle (≈ 1–2 j)

- Remplacer l'appel `hermes chat` par un **appel direct à l'API OpenRouter** (clé déjà dans `.env`),
  avec `response_format: json_schema` (schéma du CV W hub). Le modèle ne peut alors plus renvoyer de JSON invalide.
- Garder Hermes en fallback derrière un flag (`WHUB_LLM_BACKEND=openrouter|hermes`) le temps de valider.
- Modèle + fallback configurables dans `.env` (ex. primaire → secours automatique si 5xx/timeout).
- Bonus : la mise à jour automatique de Hermes ne peut plus casser la production.

## Phase 3 — Choisir le modèle sur données réelles (≈ ½ j, après phase 2)

Gemini 2.5 Flash fonctionne encore sur OpenRouter (pas de date de dépréciation annoncée), mais il a plusieurs
générations de retard. Le coût n'est pas le critère : ~0,01 $ par CV quel que soit le modèle « flash ».
On choisit sur **fidélité, JSON valide et durée**, mesurés sur les 11 CV du banc.

Candidats (prix OpenRouter du 02/11, $/M tokens entrée/sortie, tous avec sortie structurée) :

| Modèle | Prix | Pourquoi le tester |
|---|---|---|
| google/gemini-2.5-flash | 0,30 / 2,50 | référence actuelle |
| google/gemini-3.8-flash | 0,83 / 4,12 | successeur direct, même famille |
| anthropic/claude-haiku-5.5 | 0,10 / 0,50 | moins cher que l'actuel, bon en fidélité au texte |
| openai/gpt-6-luna | 0,10 / 0,50 | même gamme de prix |
| mistralai/mistral-large-4-0 | 0,70 / 2,10 | fournisseur européen (argument RGPD pour des CV candidats) |
| anthropic/claude-sonnet-5.5 | 2,00 / 10,00 | plafond de qualité, pour savoir ce qu'on perd avec un petit modèle |

Script `scripts/model_bakeoff.py` : même pipeline, modèle variable → tableau
fidélité / couverture source / JSON valide / durée / coût, + PDF côte à côte pour une relecture humaine de 3 CV.
**Décision : le meilleur score de fidélité avec 100 % de JSON valide ; à égalité, le plus rapide.**

Point RGPD à trancher en même temps : activer le « zero data retention » OpenRouter et/ou privilégier
un fournisseur UE, puisque le texte des CV passe chez le fournisseur.

## Phase 4 — Rester opérationnel

- Alerte (Telegram via Hermes, ou email) si 3 échecs consécutifs ou aucun succès en 24 h —
  la panne actuelle est passée inaperçue pendant plus de 2 semaines.
- Smoke quotidien d'1 CV fixture (cron) + digest qualité existant.
- Épingler la version Hermes ou désactiver sa mise à jour automatique tant que le fallback Hermes existe.
- Hors périmètre pour l'instant (décision du 02/11) : gates sécurité S1–S4.

## Ordre

Phase 0 tout de suite → phase 1 → phase 2 → phase 3 → phase 4.
La v2 (`feature/whub-cv-v2`, block ledger) reste en pause jusqu'à ce que `main` soit stable.
