# Audit Architecture – W hub CV Factory

**Période :** 27/05/2026  
**Scope :** `apps/web` (Next.js), `workers/cv-worker` (Python), `supabase/` (SQL), stockage & chaîne asynchrone  
**Objectif :** Identifier les failles de sécurité, points de fragilité opérationnels et proposer un plan de succession d’erreurs (fallback) robuste.

---

## 1. Vue d’ensemble de l’architecture

```
┌─────────────────────────────────────────────────────────────────────┐
│                         Vercel (Next.js App Router)                  │
│  ┌──────────┐  ┌──────────────┐  ┌──────────────┐  ┌────────────┐  │
│  │ /login    │  │ /dashboard    │  │ /requests/new│  │ /requests/[id]│  │
│  │ actions.ts│  │ (Server Comp.)│  │ actions.ts   │  │ actions.ts    │  │
│  └──────────┘  └──────────────┘  └──────────────┘  └────────────┘  │
│  Auth : Supabase SSR (anon_key) + Admin client (service_role_key)   │
└────────────────────────┬────────────────────────────────────────────┘
                         │ HTTPS / REST
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         Supabase Cloud                               │
│  ┌──────────────┐  ┌───────────────┐  ┌──────────────────────────┐  │
│  │ PostgreSQL   │  │ Storage       │  │ Auth                     │  │
│  │ - RLS        │  │ - cv-sources  │  │ - JWT sessions           │  │
│  │ - claim RPC  │  │ - cv-finals   │  │ - Whitelist allowed_users│  │
│  └──────────────┘  └───────────────┘  └──────────────────────────┘  │
└────────────────────────┬────────────────────────────────────────────┘
                         │ REST + Storage download
                         ▼
┌─────────────────────────────────────────────────────────────────────┐
│                         VPS – systemd worker                         │
│  ┌──────────────────────────────────────────────────────────────┐   │
│  │  whub-cv-worker (Python 3.11)                                │   │
│  │  ┌─────────┐ ┌──────────┐ ┌───────────┐ ┌────────┐ ┌──────┐ │   │
│  │  │ main.py │ │ extraction│ │ structuring│ │ rendering│ │ qa.py │ │   │
│  │  │ (poll)  │ │ (PyMuPDF) │ │ (Hermes CLI)│ │ (subproc)│ │      │ │   │
│  │  └─────────┘ └──────────┘ └───────────┘ └────────┘ └──────┘ │   │
│  └──────────────────────────────────────────────────────────────┘   │
│  Dépendances locales : /root/.hermes/scripts/whub_cv_renderer.py    │
│                        /tmp/poppins_full (fonts)                     │
│                        /root/.hermes/image_cache (logo, watermark)   │
└─────────────────────────────────────────────────────────────────────┘
```

---

## 2. Cartographie des composants critiques

| Composant | Responsabilité | Single Point of Failure ? |
|-----------|----------------|---------------------------|
| `apps/web` | UI, upload, auth, dashboard | Non (Vercel edge) |
| Supabase Auth & DB | Authentification, données, RLS, claim RPC | **Oui** – indisponibilité = panne totale |
| Supabase Storage | Stockage privé des PDF sources & finaux | **Oui** – outage bloque uploads et téléchargements |
| `cv-worker` | Claim, extraction, structuration, rendu, QA | **Oui** – worker unique = pas de redondance |
| `whub_cv_renderer.py` | Génération PDF depuis JSON | **Oui** – script local non versionné, pas de fallback |
| Hermes CLI (LLM) | Structuration du texte en JSON | **Oui** – pas de retry LLM externe, timeout 600s |
| `claim_next_cv_request()` RPC | Verrouillage pessimiste des jobs | Non (si réplication PostgreSQL) – mais pas de queue externe |

---

## 3. Failles de sécurité

### 🔴 Critique

#### S1. Absence totale de middleware de protection des routes
- **Fichier concerné :** toutes les pages sous `apps/web/app/`
- **Constat :** Il n’existe pas de `middleware.ts` à la racine de l’app. Chaque page fait un check `supabase.auth.getUser()` manuellement, mais des routes dynamiques ou futures pourraient oublier ce garde-fou.
- **Impact :** Exposition de données sensibles si un développeur ajoute une page sans check.
- **Correction :** Implémenter `middleware.ts` global avec matcher sur `/dashboard`, `/requests/*` et force redirect vers `/login` si JWT invalide.

#### S2. Politique RLS permissive sur `cv_requests` (lecture globale)
- **Fichier :** `supabase/migrations/002_rls.sql`
- **Constat :** `create policy "allowed users can read requests" on public.cv_requests for select to authenticated using (public.is_allowed_user());`
- **Impact :** Tout utilisateur whitelisté peut lister toutes les requêtes de tous les autres, y compris les candidats, consignes et chemins de fichiers. Risque RGPD / fuite de données candidats.
- **Correction :** Scinder la policy en `created_by = auth.uid()` pour les membres, et autoriser `admin` à tout lire. Alternative : ajouter une colonne `visibility` si le partage cross-membre est voulu.

#### S3. Code d’accès prévisible et mot de passe dérivé de l’email
- **Fichier :** `apps/web/lib/access-code.ts`
- **Constat :** `expectedAccessCodeFromEmail(email)` retourne `localPart.replace(/[^a-z0-9]/g,"")`. Le mot de passe généré côté serveur est identique au code d’accès saisi. Ex: `cdubosq@whub.fr` → mot de passe = `cdubosq`. Si un email whitelisté fuite, le mot de passe est trivial.
- **Impact :** Compromission rapide d’un compte en cas de fuite d’email whitelist.
- **Correction :** Utiliser un hash bcrypt ou Argon2 aléatoire par utilisateur stocké dans `allowed_users.hash`. Remplacer le code d’accès par un OTP/magic-link ou un secret partagé non dérivable.

#### S4. Service role key exposé au worker sans moindre privilège
- **Fichier :** `workers/cv-worker/src/supabase_client.py`
- **Constat :** Le worker utilise `create_client(url, supabase_service_role_key)` qui bypass RLS. Le fichier `.env` contient la clé en clair. Si le VPS est compromis ou si le log contient la clé, la base entière est accessible en écriture.
- **Impact :** accès complet à toutes les tables et buckets.
- **Correction :** Créer un rôle PostgreSQL dédié `whub_worker` avec `GRANT` limité aux tables nécessaires (`cv_requests`, `cv_versions`, `cv_events`, `cv_comments`). Ne pas utiliser `service_role_key`.

### 🟠 Haute

#### S5. Téléchargement de PDF sans vérification de contenu réel
- **Fichier :** `apps/web/app/requests/new/actions.ts` (ligne 27)
- **Constat :** Seul `file.type !== "application/pdf"` est contrôlé. Un attaquant peut uploader un exécutable renommé `.pdf` avec MIME `application/pdf`.
- **Impact :** Fichiers malveillants récupérés par le worker = exécution via PyMuPDF (parsing natif) ou par d’autres processus.
- **Correction :** Vérifier l’entête magique `%PDF-` côté serveur (action) et sandboxer le parsing worker (`chroot` ou container).

#### S6. Pas de rate limiting sur les Server Actions
- **Fichier :** `apps/web/app/requests/new/actions.ts`, `app/login/actions.ts`, `app/requests/[id]/actions.ts`
- **Constat :** Aucun rate limit. Un script peut inonder upload, login brute-force ou création de commentaires.
- **Impact :** DoS, coûts de stockage, brute-force du code d’accès (facile avec 4-5 caractères).
- **Correction :** Rate limiter Next.js (Vercel KV) ou ban temporaire IP sur les endpoints sensibles.

#### S7. Politique Storage `allowed users can read cv storage` est trop large
- **Fichier :** `supabase/migrations/003_storage.sql`
- **Constat :** `bucket_id in ('cv-sources','cv-finals','cv-artifacts')` + `public.is_allowed_user()`. N’importe quel utilisateur whitelisté peut lire tous les PDF de tous les buckets listés en devinant les chemins.
- **Impact :** Fuite de CV sources et finaux de candidats.
- **Correction :** Stocker le `auth.uid()` dans les métadonnées de l’objet Supabase Storage, et utiliser une policy `object owner = auth.uid()` pour les membres. Si partage cross-membre requis, générer des signed URLs à durée de vie limitée.

### 🟡 Moyenne

#### S8. Commentaires non sanitizés (risque XSS stocké réduit)
- **Fichier :** `apps/web/app/requests/[id]/page.tsx` (ligne 105)
- **Constat :** `{c.body}` est rendu en texte simple, mais s’il était interprété comme HTML un jour (éditeur riche), cela exposerait.
- **Impact :** XSS potentiel si le composant est modifié.
- **Correction :** Sanitizer systématiquement avec DOMPurify ou équivalent si passage à du HTML riche. Pour l’instant, c’est du texte simple (OK).

#### S9. Absence de Content Security Policy (CSP)
- **Constat :** Aucune CSP dans `next.config.ts`.
- **Impact :** Risque d’injection de scripts externes si une faille XSS existe.
- **Correction :** Ajouter `Content-Security-Policy` dans les headers de réponse via `next.config.ts`.

#### S10. `worker_locked_at` public mais pas vérifié dans la logique worker
- **Fichier :** `workers/cv-worker/src/main.py`
- **Constat :** Si 2 workers identiques tournent avec le même `WORKER_NAME`, ils pourraient potentiellement s’interférer (bien que `FOR UPDATE SKIP LOCKED` l’empêche côté DB).
- **Impact :** Confusion dans les logs et potentiel override de `worker_locked_by`.
- **Correction :** Vérifier en local qu’un seul processus avec ce `WORKER_NAME` tourne (fichier PID lock).

---

## 4. Points de fragilité opérationnels

### F1. Chaîne asynchrone monolithique sans file d’attente externe
- **Constat :** Le worker poll directement PostgreSQL toutes les N secondes (10s par défaut). C’est un anti-pattern pour la scalabilité.
- **Impact :** Impossible d’avoir plusieurs workers indépendants sans risque de concurrence sur la même ligne. Pas de dead-letter queue. Si le worker crash en plein milieu d’un `process_job`, le job reste en `processing` jusqu’au timeout de 30 minutes.
- **Recommandation :** Migrer vers une queue d’exécution : Supabase Realtime + Edge Functions, Cloud Tasks, Redis (BullMQ), ou SQS.

### F2. Versioning non atomique et risque d’incohérence storage ↔ DB
- **Fichier :** `workers/cv-worker/src/storage.py`
- **Constat :** `save_success()` effectue 3 uploads storage + 1 insert DB + 1 update DB sans transaction distribuée. Si l’insert `cv_versions` réussit mais l’update `cv_requests` échoue (réseau), la version est orpheline. Les uploads storage précédents sont aussi orphelins.
- **Impact :** Fichiers orphelins dans les buckets, incohérence DB.
- **Recommandation :** Utiliser une transaction Supabase ou un pattern saga : écrire d’abord en DB, puis uploader. Nettoyer les partial uploads en cas d’erreur.

### F3. Race condition sur `next_version_number()`
- **Fichier :** `workers/cv-worker/src/storage.py` (lignes 7-11)
- **Constat :** Le calcul de `version_number` est basé sur un `select … limit 1` suivi d’un `+1` puis d’un `insert`. Pas atomique.
- **Impact :** Collision de version si deux workers traitent la même requête en parallèle (après redémarrage / timeout).
- **Recommandation :** Utiliser une séquence Postgres ou une clause `DEFAULT` avec `count(*)` atomique encapsulée dans la RPC `claim_next_cv_request`.

### F4. Pas de circuit breaker / backoff sur le polling
- **Fichier :** `workers/cv-worker/src/main.py`
- **Constat :** `while True` avec `time.sleep(settings.poll_interval_seconds)` fixe. Si Supabase est down ou en surcharge, le worker continue de frapper à 10s indéfiniment.
- **Impact :** Amplification d’un incident Supabase côté client (DDoS passif).
- **Recommandation :** Backoff exponentiel sur les erreurs réseau (max 300s), avec circuit breaker après N erreurs consécutives.

### F5. Gestion mémoire / disque inadéquate
- **Fichier :** `workers/cv-worker/src/main.py`
- **Constat :** `shutil.rmtree(workdir)` au début puis jamais explicitement à la fin (hormis le nettoyage au prochain job). En cas de crash, le `/tmp/whub-cv-factory` grossit sans limite.
- **Impact :** Remplissage du disque VPS potentiel.
- **Recommandation :** `try/finally` avec cleanup explicite + cron de nettoyage des dossiers > 24h.

### F6. Pas de retry exposé aux utilisateurs
- **Constat :** Si un job passe en `failed` après 3 tentatives, l’utilisateur doit créer une nouvelle demande.
- **Impact :** Expérience utilisateur dégradée, perte du contexte.
- **Recommandation :** Bouton "Relancer la génération" côté frontend qui reset `worker_attempts=0` et `status='submitted'`.

### F7. Dépendances locales non versionnées et non déployables
- **Constat :** Le worker dépend de :
  - `/root/.hermes/scripts/whub_cv_renderer.py`
  - `/root/.hermes/image_cache/img_*.png`
  - `/tmp/poppins_full`
- **Impact :** Le VPS est un snowflake. Reconstruction sur une autre machine impossible sans documentation manuelle. Le renderer n’est pas dans ce repo.
- **Recommandation :** Dockeriser le worker avec tous les assets et polices packagés dans l’image. Versionner le renderer dans un repo séparé ou submodule.

### F8. Absence de métriques et d’alertes
- **Constat :** Aucune métrique exposée (Prometheus, StatsD, CloudWatch). Les logs restent sur STDOUT du systemd.
- **Impact :** Pas d’alerte si le worker est arrêté, si la latence de génération dépasse un seuil, ou si le taux d’erreur QA augmente.
- **Recommandation :** Endpoint `/health` avec uptime, queue depth, taux d’erreur. Alerting sur absence de heartbeat.

---

## 5. Plan de succession d’erreurs (Fallback)

### 5.1 Worker & Pipeline

```text
┌─────────────────────────────────────────────────────────────────┐
│                         Fallback Hierarchy                       │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  ┌──────────────┐     ┌────────────────┐     ┌─────────────┐    │
│  │   Happy path │     │ Degraded path  │     │ Dead path   │    │
│  │  (Worker OK) │     │ (Worker down / │     │ (Permanent  │    │
│  │              │     │  Hermes fail)  │     │   DB loss)  │    │
│  └──────┬───────┘     └───────┬────────┘     └──────┬──────┘    │
│         │                     │                      │           │
│  ┌──────▼───────┐     ┌───────▼────────┐     ┌──────▼──────┐   │
│  │ Full auto    │     │ Retry + notify │     │ Manual      │   │
│  │ generation   │     │ + expose JSON  │     │ extraction  │   │
│  │ → PDF W hub  │     │ to admin       │     │ + render    │   │
│  └──────────────┘     └────────────────┘     └─────────────┘   │
│                                                                  │
└─────────────────────────────────────────────────────────────────┘
```

#### A. Worker indisponible (process crash, VPS down)
1. **Détection :** Health check HTTP `/health` ou heartbeat écrit dans `cv_events` toutes les 60s. Datadog/Pingdom alerte après 3 échecs.
2. **Mitigation :**
   - Purger les locks anciens (`worker_locked_at < now() - interval '30 minutes'`) automatiquement via cron Supabase ou script secondaire.
   - Lancer un worker de secours sur une 2ème zone/VPS (active-passive avec systemd ou Docker Swarm).
3. **Fallback utilisateur :** Si la demande reste en `processing` > 45 min, afficher un toast "Le worker semble en pause – relance automatique en cours ou contacte un admin".

#### B. Échec de structuration Hermes (LLM down / timeout 600s)
1. **Détection :** `StructuringError` ou `subprocess.TimeoutExpired`.
2. **Mitigation :**
   - Retry avec backoff exponentiel (1min, 5min, 15min) côté worker.
   - Si 3 échecs consécutifs : basculer sur un modèle local (Ollama / local LLM) ou un prompt simplifié (mode "light structuration").
3. **Fallback utilisateur :** Exposer le texte brut extrait du PDF dans l’UI pour que l’admin puisse faire un copier/coller manuel dans le renderer ou corriger via commentaire.

#### C. Échec du renderer PDF (subprocess crash ou asset manquant)
1. **Détection :** `RenderingError` ou `returncode != 0`.
2. **Mitigation :**
   - Vérifier les assets au démarrage (`assert_whub_assets`) et les retélécharger depuis un bucket S3/GCS si absents.
   - Retry une fois le renderer.
3. **Fallback :** Si le renderer échoue définitivement, uploader le JSON structuré dans `cv-artifacts` et notifier l’admin pour génération manuelle.

#### D. QA bloquante
1. **Détection :** `QAError` (coordonnées détectées, overflow, glyph corrompu).
2. **Mitigation :** Améliorer le prompt de structuration avec les erreurs QA (annotation via LLM). Cycle de raffinement automatique (max 3 passes QA → Structuring).
3. **Fallback :** Écrire le PDF quand même mais marquer `qa_status='warning'` + blocage du téléchargement public. L’admin peut forcer le passage en `ready`.

#### E. Supabase Storage indisponible
1. **Détection :** Exception upload/download côté worker ou web.
2. **Mitigation :**
   - Buffer temporaire local (filesystem) avec retry exponentiel max 10 min.
   - Fallback vers un bucket de secours (S3 compatible) si Supabase storage est KO.
3. **Fallback :** Si indisponible > 1h, mettre le traitement en pause (status = `pending_upload`) et notifier.

#### F. Base de données PostgreSQL indisponible
1. **Détection :** Connexion refusée / timeout RPC.
2. **Mitigation :**
   - Mise en cache LRU des données critiques (profils, allowed_users) si read-only.
   - Worker en mode "buffer" : stocker les jobs finis localement (`/var/spool/whub-pending/`) et les rejouer dès que la DB revient.
3. **Fallback :** Mode maintenance côté frontend avec page statique Next.js.

### 5.2 Table de décision rapide

| Scénario | Action automatique | Fallback opérationnel |
|----------|--------------------|-----------------------|
| Worker crash | Systemd restart 5s | 2nd worker + alerte |
| Job fail x3 | Status = `failed` | Bouton "Relancer" UI |
| Hermes timeout | Retry + backoff | Prompt simplifié local |
| Renderer crash | Retry + asset check | JSON brut → manual render |
| QA contacts détectés | Loop prompt fix max 3x | Block download + flag admin |
| Supabase DB indispo | Buffer local + replay | Mode maintenance statique |
| Storage indispo | Retry 10 min + S3 mirror | Pause file d’attente |
| Version collision | Séquence PG atomique | Détection + renumérotation auto |

---

## 6. Recommandations prioritaires

| Priorité | Action | Fichier(s) | Impact sécurité | Impact perf/disponibilité |
|----------|--------|------------|-----------------|---------------------------|
| P0 | Ajouter `middleware.ts` pour protéger les routes privées | `apps/web/middleware.ts` | 🔴 Critique | 🟡 Moyen |
| P0 | Durcir RLS `cv_requests` : membres ne lisent que leurs créations | `002_rls.sql` | 🔴 Critique | 🟢 Faible |
| P0 | Remplacer le dérivé email/mot de passe par secret aléatoire + bcrypt | `lib/access-code.ts`, `login/actions.ts` | 🔴 Critique | 🟡 Moyen |
| P0 | Restreindre le worker à un rôle PostgreSQL dédié (pas service_role) | `supabase_client.py`, migrations SQL | 🔴 Critique | 🟡 Moyen |
| P1 | Rate limiting sur login et upload | `login/actions.ts`, `requests/new/actions.ts` | 🟠 Haute | 🟢 Faible |
| P1 | Vérification entête magique PDF + limite taille | `requests/new/actions.ts` | 🟠 Haute | 🟢 Faible |
| P1 | Atomicité version_number (séquence PG) | `storage.py`, `001_init.sql` | 🟠 Haute | 🟡 Moyen |
| P1 | Circuit breaker + backoff exponentiel polling | `main.py` | 🟠 Haute | 🟡 Moyen |
| P1 | Cleanup workdir en `try/finally` | `main.py` | 🟡 Moyenne | 🟡 Moyen |
| P2 | Dockeriser le worker + assets packagés | `Dockerfile`, `infra/` | 🟡 Moyenne | 🟠 Haute |
| P2 | Métriques `/health` et alerting heartbeat | `main.py`, monitoring | 🟡 Moyenne | 🔴 Critique |
| P2 | Bouton "Relancer" génération côté frontend | `requests/[id]/actions.ts`, `page.tsx` | 🟢 Faible | 🟠 Haute |
| P2 | Content-Security-Policy | `next.config.ts` | 🟡 Moyenne | 🟢 Faible |
| P3 | Signed URLs Storage (pas de paths publics) | `003_storage.sql`, downloads | 🟡 Moyenne | 🟡 Moyen |
| P3 | Migrer polling DB vers queue externe (Redis/ SQS) | Architecture globale | 🟢 Faible | 🔴 Critique |

---

## 7. Synthèse du risque global

| Axe | Score (1-5) | Justification |
|-----|-------------|---------------|
| Confidentialité données candidats | 4 | RLS permissive + storage paths publics + code d’accès faible |
| Intégrité de la chaîne de génération | 3 | Pas de transaction atomique storage/DB, versioning fragile |
| Disponibilité du service | 4 | Worker unique, pas de redondance, pas de queue externe |
| Résilience aux incidents | 2 | Absence totale de circuit breaker, retry, buffer offline |
| Observabilité | 1 | Pas de métriques, pas de health check, logs locaux uniquement |

---

*Audit réalisé sur le commit courant du repo `/root/whub-cv-factory`.*
