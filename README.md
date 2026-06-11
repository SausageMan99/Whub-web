# W hub CV Factory

W hub CV Factory est un outil interne qui transforme un CV candidat brut en CV au format W hub.

L'objectif n'est pas de “réécrire un CV avec l'IA”. L'objectif est plus strict : gagner du temps sur la production de CV tout en gardant une fidélité maximale au document source. Le système doit extraire les bonnes informations, retirer les éléments sensibles ou inutiles, générer un PDF propre, puis bloquer ou demander une vérification humaine quand il y a un doute.

## Résumé en une phrase

Un utilisateur W hub upload un PDF candidat, le worker lit et structure le contenu, génère un CV W hub, contrôle la qualité et la fidélité au CV source, puis l'interface permet de suivre, télécharger, commenter ou relancer la demande.

## À qui sert le projet

Le projet sert aux équipes W hub qui doivent transformer rapidement des CV candidats en CV présentables côté client.

Cas d'usage principal :

1. Un recruteur ou business developer reçoit un CV candidat.
2. Il l'upload dans l'interface CV Factory.
3. Il ajoute une consigne si nécessaire.
4. L'outil génère une version au format W hub.
5. L'utilisateur vérifie le résultat, télécharge le PDF, ou demande une correction.

## Ce que fait le système

Le système fait cinq choses :

1. Il reçoit un CV source au format PDF.
2. Il extrait le texte du PDF.
3. Il structure les informations candidat avec un modèle IA.
4. Il génère un PDF au format W hub.
5. Il vérifie que le résultat reste fidèle au CV source et ne contient pas d'informations interdites.

## Ce que le système ne doit pas faire

Le système ne doit pas :

1. Inventer une expérience, une compétence, une formation ou une date.
2. Supprimer une information importante présente dans le CV source.
3. Afficher ou republier des contacts candidat non souhaités.
4. Dire qu'un CV est prêt si la fidélité source est insuffisante.
5. Cacher une erreur technique derrière un statut rassurant.

## Architecture globale

Le projet est composé de quatre blocs principaux :

1. **Interface web** : application Next.js utilisée par W hub.
2. **Supabase** : base de données, stockage des fichiers et migrations.
3. **Worker Python** : traitement asynchrone des demandes CV.
4. **Renderer W hub** : génération du PDF final à partir des données structurées.

Flux simplifié :

```text
Utilisateur W hub
    ↓
Interface web Next.js
    ↓
Upload PDF dans Supabase Storage
    ↓
Création d'une ligne cv_requests en base
    ↓
Worker Python récupère la demande
    ↓
Extraction texte PDF
    ↓
Structuration IA
    ↓
Nettoyage + contrôles de fidélité
    ↓
Génération PDF W hub
    ↓
Sauvegarde version + rapport qualité
    ↓
Utilisateur télécharge ou demande une correction
```

## Stack technique

- **Frontend** : Next.js App Router, React, TypeScript, Tailwind.
- **Déploiement web** : Vercel, projet canonique `web`, root directory `apps/web`.
- **Base de données** : Supabase Postgres.
- **Storage** : Supabase Storage.
- **Worker** : Python 3.11, `uv`, systemd sur VPS.
- **IA** : appels via Hermes CLI / OpenRouter selon configuration worker.
- **PDF** : extraction avec PyMuPDF, rendu avec ReportLab et renderer W hub.
- **Queue** : BullMQ côté web en tentative d'enqueue, avec fallback polling Postgres côté worker.

## Structure du dépôt

```text
.
├── apps/web/                     # Application web Next.js
│   ├── app/                      # Routes App Router
│   ├── components/               # Composants UI
│   ├── lib/                      # Supabase, queue, helpers métier
│   └── tests/                    # Tests TypeScript web
│
├── workers/cv-worker/            # Worker Python de génération CV
│   ├── src/                      # Code métier worker
│   ├── renderer/                 # Renderer PDF W hub
│   ├── assets/                   # Logo, watermark, polices, assets W hub
│   ├── tests/                    # Tests Python worker
│   └── eval/                     # Cas d'évaluation et smoke tests
│
├── supabase/migrations/          # Schéma DB, RPC, RLS, statuts, policies
├── scripts/                      # Gates qualité et smoke tests
└── package.json                  # Workspace npm web
```

## Parcours utilisateur

### 1. Créer une demande

L'utilisateur va sur l'interface web, ouvre la page de nouvelle demande et ajoute :

- un PDF source ;
- un prénom candidat si utile ;
- des consignes optionnelles ;
- une priorité éventuelle.

Le web vérifie que le fichier est bien un PDF et qu'il ne dépasse pas la limite configurée.

Ensuite, le fichier est uploadé dans le bucket Supabase `cv-sources`, puis une ligne est créée dans `cv_requests` avec le statut `submitted`.

### 2. Suivre l'avancement

Le dashboard et la page détail affichent l'état de chaque demande.

La page détail affiche :

- le statut ;
- la progression ;
- les événements worker ;
- les versions générées ;
- les commentaires ;
- le rapport qualité redacted ;
- les actions possibles : télécharger, commenter, relancer.

### 3. Télécharger ou corriger

Si le CV est prêt, l'utilisateur télécharge le PDF final.

Si un brouillon est disponible, l'utilisateur peut le relire, ajouter une correction, puis créer une nouvelle version sans réuploader le CV source.

Si la génération échoue ou demande une vérification humaine, l'utilisateur peut relancer la demande quand le statut le permet.

## Pipeline worker détaillé

Le worker est le cœur du produit. Il tourne en continu et récupère les demandes en attente.

### Étape 1 — Claim de la demande

Le worker appelle la RPC Supabase `claim_next_cv_request`.

Cette RPC prend une demande en statut `submitted`, la verrouille, incrémente les tentatives worker, puis la passe en `processing`.

But : éviter que deux workers traitent la même demande en même temps.

### Étape 2 — Téléchargement du PDF source

Le worker récupère le fichier depuis le bucket `cv-sources`.

Le chemin du fichier vient de `cv_requests.source_file_path`.

### Étape 3 — Extraction du texte

Le worker extrait le texte du PDF source avec PyMuPDF.

Cette étape donne le texte brut qui servira à construire le CV W hub.

### Étape 4 — Profilage qualité source

Avant d'appeler l'IA, le worker analyse le texte source pour classifier le type de CV :

- `normal` ;
- `senior_long` ;
- `ats` ;
- `scanned` ;
- `two_column` ;
- `graphic` ;
- `risky` ;
- `unknown`.

Le worker produit un événement `quality_source_profiled` avec des métriques redacted : nombre de caractères, lignes, score d'extraction, profil source, etc.

Cette étape ne doit jamais stocker de contact candidat brut dans le rapport qualité.

### Étape 5 — Nettoyage du texte source

Le worker nettoie le texte pour réduire les éléments qui ne doivent pas apparaître dans le CV final, notamment les contacts candidat ou certains artefacts du PDF source.

### Étape 6 — Structuration IA

Le worker appelle le modèle IA via Hermes.

Objectif : transformer le texte source en JSON structuré exploitable par le renderer.

Le JSON doit contenir les blocs nécessaires au CV W hub : identité utile, titre, résumé, expériences, compétences, formations, outils, etc.

À ce stade, la règle importante est : l'IA structure, elle ne doit pas inventer.

### Étape 7 — Contrôles de sécurité et fidélité

Le worker vérifie notamment :

- absence de contact candidat interdit ;
- cohérence avec le CV source ;
- conservation des expériences importantes ;
- absence d'hallucination visible ;
- qualité suffisante de l'extraction ;
- capacité à générer un PDF utile.

Si la fidélité est insuffisante, la demande peut finir en `failed` avec une erreur métier comme `source_fidelity`.

Si le CV source est trop incertain ou trop pauvre, la demande peut passer en `needs_human_review`.

### Étape 8 — Mise en page

Le worker prépare les options de mise en page via le package `src/layout/`.

Ce bloc gère :

- le packing des expériences ;
- les variantes de layout ;
- les retries de mise en page ;
- la sélection de la meilleure variante ;
- les erreurs de layout bloquantes ou non bloquantes.

### Étape 9 — Rendu PDF

Le renderer W hub génère un PDF avec la charte W hub.

Les assets nécessaires sont dans `workers/cv-worker/assets/`.

Le renderer ne décide pas du contenu métier. Il transforme le JSON structuré en PDF.

### Étape 10 — Sauvegarde de la version

Quand une version est produite, le worker sauvegarde :

- le JSON structuré dans `cv-renderer-inputs` ;
- le PDF final dans `cv-finals` ;
- le rapport QA dans `cv-artifacts` ;
- une ligne dans `cv_versions` ;
- le lien vers la version courante dans `cv_requests.current_version_id`.

### Étape 11 — Événements

Le worker écrit des événements dans `cv_events`.

Ces événements servent à :

- afficher la progression ;
- diagnostiquer les incidents ;
- savoir exactement à quelle étape une demande a échoué.

## Statuts des demandes

Les statuts principaux de `cv_requests.status` sont :

- `submitted` : demande créée, en attente du worker.
- `processing` : le worker traite la demande.
- `draft_ready` : un brouillon PDF existe, mais une vérification ou correction est recommandée.
- `ready` : le CV final est prêt.
- `needs_human_review` : le système a détecté un doute qui nécessite une vérification humaine.
- `qa_failed` : la génération a produit un résultat qui ne passe pas la QA.
- `revision_requested` : un commentaire de correction a été ajouté.
- `failed` : la génération a échoué.
- `dead_letter` : la demande est considérée comme bloquée après trop d'échecs.
- `cancelled` : demande annulée.
- `archived` : demande archivée.

## Tables Supabase importantes

### `cv_requests`

Table centrale. Une ligne = une demande CV.

Contient le statut, le fichier source, les consignes, les tentatives worker, les erreurs, et la version courante.

### `cv_versions`

Une ligne = une version générée.

Contient le JSON structuré, le chemin du PDF final, le statut QA et le rapport qualité.

### `cv_comments`

Commentaires utilisateur, notamment les demandes de correction.

Une correction peut servir à créer une nouvelle version du CV.

### `cv_events`

Journal d'événements.

C'est la source la plus utile pour comprendre où une demande a échoué.

### `allowed_users` et `profiles`

Tables liées à l'authentification historique.

Attention : le projet a connu une phase de développement avec auth désactivée. Il faut donc vérifier l'état réel du middleware, des migrations et des variables d'environnement avant de considérer l'application comme prête pour une production sensible.

## Buckets Supabase

- `cv-sources` : PDFs sources uploadés par l'utilisateur.
- `cv-renderer-inputs` : JSON envoyé au renderer.
- `cv-finals` : PDFs générés au format W hub.
- `cv-artifacts` : rapports qualité, QA, artefacts de diagnostic.

## RPC Supabase importantes

### `claim_next_cv_request`

Utilisée par le worker pour prendre une demande en attente.

Elle doit être réservée au rôle worker.

### `unlock_job`

Permet de remettre une demande retryable en `submitted`.

Statuts retryables actuels :

- `failed` ;
- `dead_letter` ;
- `needs_human_review`.

Cette RPC ne doit pas être exposée publiquement. Elle doit rester limitée à `whub_worker`, `service_role` et `postgres`.

## Queue et fallback

Le web tente d'ajouter un job dans BullMQ après création d'une demande.

Mais le système garde un fallback important : même si Redis ou BullMQ est indisponible, la demande reste en `submitted` dans Postgres, et le worker peut la récupérer via polling.

Donc la source de vérité opérationnelle reste Supabase Postgres, pas Redis.

## Commandes utiles

### Installation web

Depuis la racine :

```bash
npm install
```

### Lancer le web en local

```bash
npm run dev
```

Ou directement dans le workspace :

```bash
npm run dev --workspace @whub-cv-factory/web
```

### Build web

```bash
npm run build --workspace @whub-cv-factory/web
```

### Typecheck web

```bash
npm run lint --workspace @whub-cv-factory/web
```

### Tests web

```bash
npm test --workspace @whub-cv-factory/web
```

### Tests worker ciblés qualité

```bash
cd workers/cv-worker
uv run pytest \
  tests/test_quality_report.py \
  tests/test_main_quality_report.py \
  tests/test_main_needs_human_review.py \
  tests/test_draft_ready.py \
  tests/test_main_layout_retry.py \
  tests/test_main_error_taxonomy.py \
  tests/test_eval_runner.py \
  tests/test_quality_digest.py \
  tests/test_structuring_block_coalescing.py \
  -q
```

### Gate qualité principale

Depuis la racine :

```bash
./scripts/verify_quality_loop.sh
```

Cette commande vérifie la boucle qualité worker + web et valide les cas d'évaluation.

### Gate complète

Depuis la racine :

```bash
./scripts/verify_all.sh
```

Cette commande sert de vérification plus large avant release.

### Smoke E2E

```bash
python3 scripts/e2e_smoke.py chemin/vers/cv.pdf
```

Le smoke upload un PDF, crée une demande, attend le worker, puis inspecte le résultat.

Important : un smoke peut valider que la boucle qualité tourne tout en terminant en `failed` si la fidélité source est insuffisante. Dans ce cas, ce n'est pas forcément un crash technique ; c'est potentiellement un blocage métier du quality gate.

## Déploiement

### Web

Le web est déployé sur Vercel.

Projet canonique : `web`.

Root directory Vercel : `apps/web`.

Déploiement manuel :

```bash
cd apps/web
vercel deploy --prod --yes
```

Inspection du déploiement :

```bash
vercel inspect web-topaz-zeta-hpye9vj4d1.vercel.app
```

### Worker

Le worker tourne via systemd sur le VPS.

Commandes utiles :

```bash
systemctl restart whub-cv-worker.service
systemctl is-active whub-cv-worker.service
systemctl show -p MainPID --value whub-cv-worker.service
journalctl -u whub-cv-worker.service -n 100 --no-pager
```

Un déploiement Vercel ne redémarre pas le worker. Si le code worker change, il faut redémarrer `whub-cv-worker.service` séparément.

## Variables d'environnement principales

### Web

Variables typiques côté `apps/web/.env.local` ou Vercel :

- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`
- `REDIS_URL` si BullMQ est activé

### Worker

Variables typiques côté `workers/cv-worker/.env` ou service systemd :

- `SUPABASE_URL`
- `SUPABASE_ANON_KEY`
- `WORKER_DATABASE_URL`
- `WORKER_NAME`
- `POLL_INTERVAL_SECONDS`
- `MAX_ATTEMPTS`
- `WHUB_PRIMARY_PROVIDER`
- `WHUB_PRIMARY_MODEL`
- `HERMES_PROFILE`
- `WHUB_RENDERER_PATH`
- `WHUB_ASSETS_DIR`
- `WHUB_FONTS_DIR`

Le worker doit utiliser le rôle Postgres `whub_worker` via `WORKER_DATABASE_URL` pour les opérations DB. Le service role Supabase ne doit pas être le chemin normal du worker.

## Diagnostic d'une demande bloquée

Pour diagnostiquer une demande, ne pas se fier uniquement à l'UI.

Toujours regarder dans cet ordre :

1. La ligne `cv_requests`.
2. Les événements `cv_events`.
3. Les versions `cv_versions`.
4. Le journal systemd du worker.
5. Les artefacts éventuels dans Supabase Storage.

Exemple de questions à résoudre :

- Quel est le statut exact ?
- À quelle étape le worker s'est arrêté ?
- Le fichier source est-il accessible ?
- L'événement `quality_source_profiled` existe-t-il ?
- Une version a-t-elle été sauvegardée ?
- Le PDF final existe-t-il dans `cv-finals` ?
- L'erreur est-elle technique ou métier ?

## Erreurs fréquentes

### `Module not found: Can't resolve '@/lib/queue'`

Cause probable : un fichier existe localement mais n'a pas été commit.

Action : vérifier `git status`, ajouter le module manquant, relancer le build Vercel.

### Le build Vercel passe mais le worker ne change pas

Normal : Vercel ne déploie que le web.

Action : redémarrer `whub-cv-worker.service`.

### La demande reste en `submitted`

Causes possibles :

- worker arrêté ;
- RPC `claim_next_cv_request` cassée ;
- connexion DB worker invalide ;
- circuit breaker worker ouvert ;
- worker en train de traiter une autre demande longue.

### La demande finit en `failed` avec `source_fidelity`

Cela signifie que le système estime que le CV généré n'est pas assez fidèle au CV source.

Ce n'est pas forcément une panne infra. C'est souvent un problème de qualité d'extraction, de structuration IA ou de règles de fidélité trop strictes ou mal calibrées.

### Le PDF existe mais le statut n'est pas clair

Regarder `cv_versions`, `current_version_id`, `qa_status` et les événements `cv_events`.

## Règles qualité importantes

- Le rapport qualité doit être redacted : pas d'email, téléphone, LinkedIn, GitHub ou URL candidat brute.
- Un CV avec contact candidat interdit doit être bloqué.
- Les statuts doivent refléter la réalité du pipeline.
- Une demande relançable doit pouvoir être relancée côté backend, pas seulement affichée comme relançable côté UI.
- Un test local n'est pas suffisant si le code dépend de fichiers non commités.
- Le worker doit être reconstructible depuis un clone propre du dépôt.

## Schéma détaillé du fonctionnement

Cette section rassemble tout ce qu'il faut connaître pour interroger le projet de manière précise : modèle de données, cycle de vie d'une demande, événements émis, structure des rapports qualité, buckets de stockage, RPC, et catégorisation des erreurs.

### 1. Architecture logique

```text
┌─────────────────────────────────────────────────────────────────────┐
│  NAVIGATEUR W hub (utilisateur authentifié ou dev no-auth)         │
└───────────────────────────────┬─────────────────────────────────────┘
                                │ HTTPS
                                ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Next.js (apps/web) — Vercel                                        │
│  ├─ app/  : routes App Router (login, dashboard, requests/*)       │
│  ├─ lib/  : supabase admin, queue BullMQ, rate-limit, helpers UI   │
│  └─ actions.ts : server actions (prepareUpload, createRequest,      │
│                  addComment, retryRequest)                          │
└──────┬──────────────────────────────────┬────────────────────────────┘
       │ Service Role (admin)            │ Tentative d'enqueue BullMQ
       ▼                                  ▼
┌──────────────────────┐         ┌──────────────────────┐
│  Supabase Postgres   │         │  Redis (optionnel)   │
│  + Storage (4 buckets)│        │  BullMQ              │
└──────┬───────────────┘         └──────────┬───────────┘
       │ RPC whub_worker                    │
       │ claim_next_cv_request              │
       ▼                                    │
┌──────────────────────────────────────────┴─────────────────────────┐
│  Worker Python (systemd : whub-cv-worker.service, sur le VPS)        │
│  ├─ main.py          : boucle poll + process_job                    │
│  ├─ extraction.py    : PyMuPDF                                       │
│  ├─ source_sanitizer : retrait contacts/liens/adresses              │
│  ├─ quality_report.py: QualityReportBuilder + classify_source_profile│
│  ├─ structuring.py   : appel Hermes (minimax-m3) + assert_no_contact│
│  ├─ layout/          : packing + variants + retry                   │
│  ├─ rendering.py     : appelle renderer/whub_cv_renderer.py         │
│  ├─ qa.py            : run_qa, classify_qa_report                   │
│  └─ storage.py       : upload input.json / final.pdf / qa.json     │
└──────┬──────────────────────────────────────────────────────────────┘
       │ INSERT/UPDATE
       ▼
┌─────────────────────────────────────────────────────────────────────┐
│  Supabase Postgres — tables applicatives                            │
│  cv_requests · cv_versions · cv_comments · cv_events                │
└─────────────────────────────────────────────────────────────────────┘
```

Le worker n'a qu'un seul chemin d'entrée vers la base : le rôle Postgres `whub_worker` (RPC + service role via `WORKER_DATABASE_URL`). Redis/BullMQ est secondaire ; si Redis tombe, le polling Postgres continue.

### 2. Modèle de données (Postgres)

```text
allowed_users          profiles                 cv_requests
┌─────────────┐        ┌──────────────┐         ┌──────────────────────────────────────┐
│ email PK    │◀──FK──▶│ id PK        │◀──FK────│ id PK                                │
│ role        │        │ email        │         │ created_by FK → profiles.id          │
│ created_at  │        │ full_name    │         │ title                                │
└─────────────┘        │ role         │         │ candidate_first_name                 │
                       │ created_at   │         │ candidate_internal_label             │
                       └──────────────┘         │ source_file_path                     │
                                                │ source_file_name                     │
                                                │ source_file_mime / size              │
                                                │ instructions                         │
                                                │ priority ∈ {normal, high, urgent}    │
                                                │ status (cf. §3)                      │
                                                │ current_version_id (FK optionnelle)  │
                                                │ worker_locked_at / worker_locked_by  │
                                                │ worker_attempts                      │
                                                │ last_error                           │
                                                │ submitted_at / started_at / ready_at │
                                                │ created_at / updated_at              │
                                                └──────┬───────────────────────┬───────┘
                                                       │                       │
                                                       ▼                       ▼
                          cv_versions                              cv_events
                          ┌────────────────────────────────┐      ┌────────────────────────┐
                          │ id PK                          │      │ id PK                  │
                          │ request_id FK                  │      │ request_id FK          │
                          │ version_number                 │      │ actor_id FK (nullable) │
                          │ structured_json                │      │ actor_type ∈           │
                          │ renderer_input_path            │      │   {user, worker, sys}  │
                          │ final_pdf_path                 │      │ event_type (cf. §4)    │
                          │ qa_status ∈ {pending,passed,   │      │ payload (jsonb)        │
                          │              failed,draft}     │      │ created_at             │
                          │ qa_report (jsonb)              │      └────────────────────────┘
                          │ generated_by                   │
                          │ generated_at                   │
                          └────────────────────────────────┘

                          cv_comments
                          ┌────────────────────────────────┐
                          │ id PK                          │
                          │ request_id FK                  │
                          │ version_id FK (nullable)      │
                          │ author_id FK → profiles.id     │
                          │ body                           │
                          │ comment_type ∈                 │
                          │   {general, revision, qa,      │
                          │    internal, history}          │
                          │ metadata (jsonb) — depuis 017  │
                          │ resolved, resolved_at          │
                          │ created_at                     │
                          └────────────────────────────────┘
```

Les versions ont `unique(request_id, version_number)`. Les commentaires de révision `metadata.category` sont filtrés par allowlist côté server action.

### 3. Machine à états d'une demande

```text
              ┌──────────┐
              │ submitted│
              └────┬─────┘
                   │ claim_next_cv_request()
                   ▼
              ┌───────────┐
              │ processing│
              └────┬──────┘
                   │
       ┌───────────┼─────────────┬──────────────┐
       │                           │             │
       ▼                           ▼             ▼
┌─────────────────┐  ┌──────────────────┐  ┌──────────────┐
│ needs_human_    │  │      failed      │  │  qa_failed   │
│ review          │  │  + event_type    │  │ (layout hard)│
│ (extraction     │  │  = "failed"      │  └──────┬───────┘
│  trop pauvre)   │  └────────┬─────────┘         │
└──────┬──────────┘           │                   │
       │                      │ unlock_job()      │ unlock_job()
       │                      │ (RPC, whub_worker │ (nouvelle politique)
       │                      │  + service_role)  │
       │                      ▼                   │
       │                 ┌──────────┐            │
       │                 │ submitted│            │
       │                 └──────────┘            │
       │ unlock_job()                            │
       └──────────▶ submitted                    │
                                                │
   (depuis ready / draft_ready via commentaire)  │
                                                ▼
                                       ┌──────────────────┐
                                       │ revision_requested│
                                       └────────┬─────────┘
                                                │
                                                ▼
                                       (re-claim, re-processing)
                                                │
                                                ▼
                                       ┌──────────────────┐
                                       │   draft_ready    │──▶ téléchargeable + correction
                                       └────────┬─────────┘
                                                ▼
                                       ┌──────────────────┐
                                       │      ready       │──▶ PDF final validé
                                       └────────┬─────────┘
                                                │
                                                ▼
                                       ┌──────────────────┐
                                       │   cancelled      │ / archived (action manuelle)
                                       └──────────────────┘
```

Statuts finaux (verrouillés sauf intervention) :

`ready`, `failed`, `qa_failed`, `dead_letter`, `cancelled`, `archived`, `needs_human_review` (avant retry).

### 4. Séquence d'événements `cv_events` pour un run nominal

```text
worker_claimed               → le worker a lock la demande
extraction_done              → texte PDF extrait (payload: {chars: N})
quality_source_profiled      → profil source classifié (payload: {source_profile, scores, metrics})
source_sanitized             → counts de sanitization (payload: {removed_email_count, removed_phone_count, …})
layout_variant_selected      → uniquement si attempts_count > 1 (payload: {selected, attempts_count})
draft_ready  OU  ready       → fin de run (payload: {version_id, version_number, layout_warnings?, fidelity_warnings?})
```

En cas d'échec :

```text
failed        → payload: {error, error_category, fidelity_issues?, contact_categories?, contact_paths?}
qa_failed     → idem avec last_error court
needs_human_review → payload: {source_profile, reason: "extraction_low_confidence"}
```

L'événement `unlocked` est émis par la RPC `unlock_job` quand on remet une demande en `submitted`.

### 5. Pipeline worker — étapes et timings

Chaque run de `process_job` mesure ces timings et les log en fin de course :

```text
download_source              (téléchargement depuis cv-sources)
extract_text                 (PyMuPDF)
load_comments                (SELECT cv_comments non résolus)
hermes_structuring           (appel modèle + repair + coalesce)
render_pdf_qa_layout_variants (layout: base + retry)
upload_and_finalize          (save_version + INSERT cv_versions)
```

Et en plus, les events profil / sanitization sont émis au fil de l'eau.

### 6. Buckets de stockage et leur rôle

```text
cv-sources/        {request_id}/source/{filename}    → PDF candidat uploadé (privé)
cv-renderer-inputs/ {request_id}/v{N}/input.json     → JSON structuré envoyé au renderer
cv-finals/         {request_id}/v{N}/cv-whub.pdf     → PDF final W hub
cv-artifacts/      {request_id}/v{N}/qa.json         → rapport QA complet (raw)
```

Politiques : `cv-sources` est privé, `cv-renderer-inputs` et `cv-finals` ont une policy publique en lecture pour permettre le download via URL signée longue.

### 7. RPC Supabase

```text
claim_next_cv_request(worker_name)        -- whub_worker + service_role + postgres
  → SELECT … WHERE status='submitted' … FOR UPDATE SKIP LOCKED
  → UPDATE status='processing', worker_locked_at=now, worker_locked_by=worker_name,
                       worker_attempts=worker_attempts+1
  → retourne la ligne complète

unlock_job(p_request_id)                  -- whub_worker + service_role + postgres (plus PUBLIC/anon/authenticated)
  → SELECT … WHERE status IN ('failed','dead_letter','needs_human_review') FOR UPDATE
  → UPDATE status='submitted', worker_attempts=0, last_error=null, worker_locked_*=null
  → INSERT cv_events(event_type='unlocked')
  → retourne la ligne complète
```

### 8. Profils source détectés

`quality_report.classify_source_profile` classe le texte brut :

```text
ats             ≥ 3 markers TJM/dispo/mobilité/permis/salaire
scanned         < 250 chars et 0 marker ATS
senior_long     > 9000 chars ou ≥ 10 markers mission/projet/client/exp…
two_column      short_line_ratio > 0.58 et > 45 lignes
normal          défaut
graphic         (réservé)
risky           (réservé)
unknown         (fallback)
```

Le score d'extraction démarre à 88/100, descend à 72 pour `two_column`/`risky`, à 35 pour `scanned`. En dessous de 500 chars sur un profil scanné, ou sous 250 chars / 5 lignes, `should_require_human_review` renvoie `True` → la demande passe en `needs_human_review` sans appel LLM.

### 9. Catégories d'erreurs (cf. `classify_structuring_error`)

Chaque erreur est classée en une seule catégorie avec un message public safe :

```text
contact_leak                   → email/téléphone/LinkedIn/GitHub dans le JSON
identity_leak                  → nom de famille candidat dans zone interdite
source_fidelity                → reformulation, hallucination, fait absent du CV source
source_sanitization            → sanitizer a retiré trop de contenu
structuring_invalid_json       → JSON Hermès ou renderer invalide/incomplet
layout_density                 → page_too_dense, page_too_sparse, overflow, orphan
renderer_asset                 → logo/watermark/asset manquant
missing_candidate_first_name   → pas de pattern Prénom NOM détectable
transient_model_failure        → timeout, fallback, crash
```

La catégorie est exposée dans `cv_events.payload.error_category` (clé standardisée). L'utilisateur final ne voit que le message public, jamais la stack.

### 10. Structure du `cv_versions.qa_report`

Le rapport attaché à chaque version contient un bloc `quality_report` ajouté en fin de process :

```text
{
  source_profile: "senior_long",
  scores: {
    extraction: 88,
    layout: 76,
    fidelity: 100,
    overall: 76     // = min(layout, fidelity)
  },
  metrics: {
    raw_chars, sanitized_chars, line_count,
    pages, attempts_count, total_duration_seconds,
    mission_markers, ats_markers, short_line_ratio,
    final_qa_status
  },
  hard_blockers: [ { code, stage, ... } ],   // bloquent la publication
  soft_warnings: [ { code, stage, page?, ... } ],  // affichés en UI, n bloquent pas
  layout_issues: [ { code, page, message } ]      // détail brut (privé, jamais affiché)
}
```

`assert_quality_report_is_redacted` refuse tout rapport contenant un email, téléphone, URL ou LinkedIn/GitHub détectable. Cette contrainte est testée.

### 11. Pages Next.js et leur contrat

```text
/                              → landing (auth-dev redirect)
/login                         → formulaire code d'accès (no-auth en dev)
/auth/callback                 → handler magic link (peu utilisé en dev no-auth)
/dashboard                     → liste des cv_requests (status, priorité, demandeur)
/requests/new                  → formulaire d'upload + consigne
/requests/[id]                 → détail : avancement, version courante, versions précédentes,
                                qualité CV, commentaires, retry, download
/requests/[id]/download/[versionId]  → signed URL cv-finals, content-disposition filename
```

Server actions (`apps/web/app/requests/*/actions.ts`) : `prepareUpload`, `createRequest`, `addComment`, `retryRequest`. Toutes passent par `createSupabaseAdminClient()` (service role) et sont rate-limited via `lib/rate-limit`.

### 12. Files d'attente

```text
Web (lib/queue) ──tentative──▶ BullMQ (Redis) ─────┐
                                                  │ (si Redis OK)
                                                  ▼
                                Worker queue consumer (src/queue/consumer.py)
                                                  │
                                                  └─ sinon fallback : polling Postgres

Postgres (cv_requests WHERE status='submitted')  ◀── worker poll_with_backoff() 10s
```

BullMQ côté web, c'est du best-effort. La source de vérité opérationnelle reste Postgres.

### 13. Requêtes utiles pour audit et amélioration

Quelques patterns SQL reproductibles via `supabase db query --linked` :

```sql
-- 1. Demandes bloquées plus de 5 minutes en processing
select id, status, worker_locked_at, worker_locked_by, last_error
from cv_requests
where status = 'processing'
  and worker_locked_at < now() - interval '5 minutes';

-- 2. Profil source dominant sur les 7 derniers jours
select payload->>'source_profile' as profile, count(*) as n
from cv_events
where event_type = 'quality_source_profiled'
  and created_at > now() - interval '7 days'
group by 1 order by n desc;

-- 3. Catégories d'échec sur 30 jours
select payload->>'error_category' as category, count(*) as n
from cv_events
where event_type in ('failed','qa_failed')
  and created_at > now() - interval '30 days'
group by 1 order by n desc;

-- 4. Versions avec score global < 60 (qualité suspecte)
select request_id, version_number, qa_status,
       (qa_report->'quality_report'->'scores'->>'overall')::int as overall
from cv_versions
where (qa_report->'quality_report'->'scores'->>'overall')::int < 60
order by generated_at desc
limit 20;

-- 5. Demandes retryable en attente d'action humaine
select id, status, last_error, candidate_first_name
from cv_requests
where status in ('failed','dead_letter','needs_human_review')
  and updated_at < now() - interval '1 hour'
order by updated_at;
```

Ces requêtes couvrent : incidents worker bloqués, observabilité qualité, audit d'erreurs, scoring de versions, file d'attente humaine.

## Workflow recommandé avant release

1. Vérifier le diff Git.
2. Lancer `./scripts/verify_quality_loop.sh`.
3. Lancer `npm run build --workspace @whub-cv-factory/web`.
4. Tester le worker sur un checkout propre si des fichiers worker ont changé.
5. Appliquer les migrations Supabase si nécessaire.
6. Pusher sur `main`.
7. Déployer Vercel.
8. Redémarrer le worker si nécessaire.
9. Lancer un smoke E2E avec un vrai PDF.
10. Vérifier `cv_requests`, `cv_events`, `cv_versions` et `journalctl`.

## État de maturité

Le projet est fonctionnel mais doit être considéré comme un outil en stabilisation.

Les zones les plus critiques sont :

1. Fidélité au CV source.
2. Statuts compréhensibles pour W hub.
3. Sécurité et confidentialité des CV.
4. Reproductibilité depuis GitHub.
5. Observabilité des erreurs worker.

Tant que ces cinq points ne sont pas solides, il faut éviter de présenter le projet comme une production totalement mature.

## Explication courte pour non-technique

CV Factory est un outil interne W hub qui prend un CV candidat brut, extrait les informations importantes, les remet dans un modèle W hub, génère un PDF propre et vérifie automatiquement que le contenu reste fidèle au CV original.

L'équipe peut suivre l'avancement, télécharger le CV généré, demander une correction ou relancer une demande si le système détecte un problème.

Le but est de produire des CV W hub plus vite, sans perdre la fiabilité ni inventer d'informations candidat.
