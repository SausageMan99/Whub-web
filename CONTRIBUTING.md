# Contributing — W hub CV Factory

Ce document décrit les règles minimales pour contribuer au projet sans casser la prod.

## Branches

- `main` est la seule branche de longue durée. Elle est protégée.
- Aucun push direct sur `main`. Tout passe par une Pull Request.
- Branches de travail : `feat/<slug>`, `fix/<slug>`, `chore/<slug>`, `docs/<slug>`.
- Squash merge uniquement. Pas de merge commit.
- Une fois mergé, la branche est supprimée.

### Branch protection (à activer dans GitHub Settings)

- Require pull request before merging : ON
- Require approvals : 1 (toi-même pour solo)
- Dismiss stale pull request approvals when new commits are pushed : ON
- Require status checks to pass before merging : ON
  - Sélectionner : `verify-quality` et `verify-build`
- Require linear history : ON
- Include administrators : ON
- Allow force pushes : OFF
- Allow deletions : OFF

Pour configurer via API, voir `scripts/setup-branch-protection.sh` (à lancer avec un token admin).

## Convention de commits

Format strict : `type(scope): sujet` en français ou anglais, sujet sans majuscule, sans point final.

| Type | Usage |
|---|---|
| `feat` | Nouvelle fonctionnalité utilisateur |
| `fix` | Correction de bug |
| `chore` | Tâche sans impact utilisateur (deps, config, scripts) |
| `docs` | Documentation uniquement |
| `refactor` | Restructuration sans changement fonctionnel |
| `test` | Ajout ou correction de tests |
| `perf` | Amélioration de performance |
| `security` | Correctif de sécurité |

`scope` est un des : `web`, `worker`, `supabase`, `queue`, `infra`, `docs`, `ci`, `readme`.

Exemples valides :
- `feat(web): add needs_human_review status to request detail`
- `fix(worker): coalesce heading-only blocks before Hermes call`
- `chore(ci): add verify-quality workflow`
- `docs(readme): document storage buckets`

Exemples invalides :
- `update code` : pas de type, pas de scope
- `feat(web): Add feature.` : majuscule et point final
- `fix: bug` : scope manquant

## Tests et gates

Avant chaque push, le hook `.githooks/pre-push` exécute :

1. `npm run build --workspace @whub-cv-factory/web`
2. `./scripts/verify_quality_loop.sh`

Si un des deux échoue, le push est annulé. Pour bypasser temporairement (urgence uniquement) :

```bash
git push --no-verify
```

Les GitHub Actions rejouent les mêmes checks sur chaque PR. Voir `.github/workflows/ci.yml`.

## Releases et tags

Chaque release est taggée `vX.Y.Z` au merge sur `main`. Format semver :

- `X` (major) : breaking change API ou DB
- `Y` (minor) : nouvelle fonctionnalité rétrocompatible
- `Z` (patch) : bugfix rétrocompatible

Tag exemple : `git tag -a v0.1.0 dd61fb0 -m "MVP post-eval loop"`.

Pour lister les tags : `git tag -l "v*"`.

## Pull Request

PR doit contenir :

- Titre conventional commit
- Description : problème, solution, impact
- Si modif DB : lien vers migration
- Si modif worker : preuve de test (logs, événements)
- Captures ou extraits si UI touchée

Checklist avant demande de review :

- [ ] `npm run build --workspace @whub-cv-factory/web` passe
- [ ] `./scripts/verify_quality_loop.sh` passe
- [ ] Pas de secret dans le diff
- [ ] Pas de log debug oublié
- [ ] Pas de TODO sans ticket

## Worker — règles spécifiques

- Ne jamais committer `workers/cv-worker/renderer/output_*.pdf` (générés)
- Toute modif worker doit être suivie d'un `systemctl restart whub-cv-worker.service`
- Tout changement de statut, event_type, ou catégorie d'erreur = bump du scope dans le commit
- `assert_quality_report_is_redacted` doit toujours passer : pas de contact dans les rapports

## Supabase

- Toute nouvelle migration commence par un numéro libre suivant le dernier `0XX_*.sql`
- Migration doit être idempotente (`if not exists`, `drop if exists`)
- RPC exposée doit être testée par au moins un test SQL ou worker
- Pas de RLS ouverte par défaut
