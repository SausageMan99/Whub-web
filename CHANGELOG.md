# Changelog

Toutes les modifications notables du projet sont documentées ici. Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/), et le projet adhère au [Semantic Versioning](https://semver.org/lang/fr/).

## [Unreleased]

### À venir
- Branch protection sur `main` (à activer via `scripts/setup-branch-protection.sh`)
- Pre-push gate via `.githooks/pre-push`
- CI GitHub Actions via `.github/workflows/ci.yml`

## [0.1.0] - 2026-06-11

Premier état de prod stable après stabilisation des quality loops.

### Ajouté
- Boucle d'auto-évaluation avec quality reports redacted (extraction, source profile).
- Statut `needs_human_review` pour CV source trop pauvre ou incertain.
- Statut `dead_letter` pour demandes bloquées après trop d'échecs.
- Statut `draft_ready` téléchargeable avec possibilité de relance par commentaire.
- 4 cas d'évaluation offline (`example`, `ats_hellowork_boilerplate`, `scanned_low_confidence`, `two_column_date_role`).
- `scripts/verify_quality_loop.sh` comme gate de pre-push.
- `scripts/e2e_smoke.py` pour valider la boucle qualité en bout-en-bout.
- Layout packer + variants (base + retry borné) avec sélection déterministe.
- Profile classifier : `normal`, `senior_long`, `ats`, `scanned`, `two_column`, `graphic`, `risky`, `unknown`.
- Bucket `cv-renderer-inputs` et policies publiques de download.
- Bucket `cv-finals` avec signed URL.
- `cv_comments.metadata` pour catégoriser les demandes de correction.
- Server actions rate-limited (`login`, `upload`, `comment`, `retry`).
- README détaillé avec schéma complet du système.
- 4 commits de stabilisation critique : `340fcd1` (queue producer), `27ce6c2` (layout worker + Supabase), `f3fc924` (README), `dd61fb0` (schema détaillé).

### Sécurité
- RPC `unlock_job` restreinte à `whub_worker`, `service_role`, `postgres`. Plus accessible par `anon`/`authenticated`/`PUBLIC`.
- RPC `unlock_job` étendue à `needs_human_review` (était `failed`/`dead_letter` uniquement).
- `assert_quality_report_is_redacted` bloque tout contact candidat dans les rapports qualité.

### Connu
- 3 commits historiques (`9e1f8bc`, `cae9863`, `a0e6042`) ont un build Vercel rouge parce qu'ils référençaient `@/lib/queue` avant que le package soit ajouté. Le fix est dans `340fcd1`. Pas d'impact sur la prod actuelle.
- Auth désactivée en dev (no-auth mode) par décision projet. À réactiver pour mise en prod réelle.
- Auth des server actions repose sur `createSupabaseAdminClient()` (service role) avec rate limiting. Pas d'auth utilisateur final.

[Unreleased]: https://github.com/SausageMan99/Whub-web/compare/dd61fb0...HEAD
[0.1.0]: https://github.com/SausageMan99/Whub-web/releases/tag/v0.1.0
