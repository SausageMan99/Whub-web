# Changelog

Toutes les modifications notables du projet sont documentées ici. Le format suit [Keep a Changelog](https://keepachangelog.com/fr/1.1.0/), et le projet adhère au [Semantic Versioning](https://semver.org/lang/fr/).

## [Unreleased]

### Interface : la table de relecture
- **Un seul écran de travail `/demandes`** : la file des demandes à gauche, regroupée par action (à relire, en cours, bloqués, prêts à envoyer), avec recherche par prénom ou poste ; la demande ouverte au centre. `/`, `/dashboard`, `/requests/[id]` et `/requests/new` redirigent vers ce nouvel écran.
- **Épreuve affichée dans la page** avec pdf.js (`/demandes/[id]/apercu/[versionId]` sert le PDF depuis le même domaine). Les points à vérifier du rapport qualité sont traduits en français clair, placés sur la page concernée (la zone vide d'une page presque vide est encadrée) et proposent une correction pré-remplie.
- **Statut « Prêt à envoyer »** : la personne qui relit valide la dernière version. Sans migration : événement `human_validated` (et `human_validation_cancelled`) dans `cv_events`, avec la version et le prénom.
- **Prénom du relecteur** gardé dans le navigateur (sans compte) ; il signe validations et corrections (`cv_comments.metadata.author`).
- **Nouveau CV** dans une fenêtre ; glisser-déposer qui fonctionne partout dans l'écran ; le prénom est deviné depuis le nom du fichier ; seul l'en-tête du PDF est lu pour le contrôle.
- **Présentation des nouveautés** au premier lancement, rouvrable depuis « Nouveautés ».
- Nouveaux tokens de couleur et Poppins dans `globals.css` ; `tailwind.config.ts` (ignoré par Tailwind 4) supprimé.

### Corrigé
- Les numéros de version affichés venaient d'une séquence globale (« Version 246 ») : ils sont maintenant numérotés 1, 2, 3 par demande, y compris dans le nom du PDF téléchargé.
- Les pages lisaient `cv_events.metadata`, une colonne qui n'existe pas (c'est `payload`) : le suivi des étapes et les badges ne s'affichaient jamais.
- Le halo de l'ancienne page d'accueil masquait le bouton principal ; la zone « Dépose le PDF ici » n'acceptait pas le glisser-déposer.
- Le nom du fichier source (souvent avec le nom de famille) n'est plus affiché.
- **Moteur : les corrections sur les compétences ont un effet.** Un commentaire de révision qui modifie les compétences (« supprime la catégorie Projets », « retire les doublons ») n'est plus annulé par la fusion des compétences source, la réinjection des faits source ni la lecture des styles du PDF ; les faits retirés à la demande sont tracés dans `_revision_removed_source_facts` et ne sont plus signalés par la QA (demande « Test-Clément », 3 novembre 2026).
- **Moteur : la formation ne fuit plus dans les compétences.** Une année seule sur sa ligne (colonne formations lue entre deux lignes de compétences) termine le fait source : « API REST Node.js » n'absorbe plus « 2014 Licence Informatique Université Paris Cité » (même cas chez Zahia). « plateforme Th@Bot » n'est plus écarté comme une adresse e-mail. Une compétence qui contient un diplôme ou une école donne l'avertissement `skill_item_contains_formation` (CV en brouillon à relire).

### Accès libre encadré
- `noindex` et `robots.txt` (`Disallow: /`) ; page `/login` supprimée (elle affichait la règle du code d'accès).
- Dépendances du front figées sur les versions du lockfile au lieu de `latest`.

### Connu
- 18 tests hérités échouent comme avant cette branche (`download`, `middleware`, `retryRequest`) : ils supposent l'authentification, désactivée.
- Le limiteur de débit garde ses compteurs en mémoire tant qu'Upstash n'est pas configuré.

### À venir
- Branch protection sur `main` (à activer via `scripts/setup-branch-protection.sh`)
- Pre-push gate via `.githooks/pre-push`
- CI GitHub Actions via `.github/workflows/ci.yml`

## [0.2.0] - 2026-11-03

Remise en service après la panne du 16 au 30/10/2026, puis fiabilisation de la fidélité et de la mise en page. Banc prod : 9/11 le 02/11, puis 11/11 dont 8 ready le 03/11 (3 ready le matin du 03/11).

### Corrigé
- **Panne d'octobre** : Hermes v0.22 refusait `--source whub-cv-worker` (`invalid_params`). Le worker utilise `--source tool` (`170df53`), et 9 des 10 demandes bloquées ont été récupérées.
- **Rejet de version** : un CV dont la QA passait mais qui avait des alertes de fidélité douces était rejeté par `save_version` (« draft_ready requests must carry a non-passing QA report », cas Heidi). Le rapport est désormais marqué `passed: false` + `draft_override_reason` (`9d86470`).
- La rétrogradation après une révision de mise en page comparait à `"ready"` au lieu de `"passed"`.
- Les commentaires de révision qui portent sur les compétences ou les catégories déclenchent une révision de contenu, plus seulement un nouveau rendu (`3612b4d`).
- **CV longs découpés en blocs** (`8f9bfcf`) : les langues et certifications de tous les blocs sont conservées, et une expérience séparée de ses missions est recollée (cas Amina).
- **Le nettoyage de la source n'altère plus le texte** (`8584ad3`) :
  - `ASP.NET`, `ADO.NET`, `VB.NET` ne sont plus supprimés comme noms de domaine ;
  - les lignes sans coordonnée gardent leur ponctuation (« : », « ; », virgules, puces).
- **Le nettoyage du JSON n'efface plus de mots** (`8584ad3`) : « LinkedIn », « contact », « email » ne sont plus retirés des phrases sans coordonnée (« campagnes LinkedIn Ads »).
- Les ligatures PDF (« ﬁ », « ﬂ »…) sont écrites en lettres normales à l'extraction (`8584ad3`).
- Les titres en lettres espacées (« E X P É R I E N C E S ») ferment la section Compétences du parseur de secours (`8584ad3`).
- **Fausses alertes de couverture des expériences** (`047fba2`), sur oussama, hodard, rayan et yannick :
  - date seule sur sa ligne, puis poste ;
  - prénom et titre répétés en haut de page ;
  - colonne latérale entre deux pages de missions ;
  - titres « (suite) » / « — suite » ;
  - champs « Libellé : valeur » collés à une mission.
- Les puces de polices symboles (Wingdings) et les sous-puces Word « o » isolées deviennent « • texte » à l'extraction (`047fba2`).
- Le parseur de compétences de secours ne coupe plus aux virgules entre parenthèses (`047fba2`).
- **Pagination** (`c5707ca`) :
  - plus de dernière page presque vide (zahia, noel) ni de page de suite à 33 % (amina) ;
  - plus de titre d'expérience orphelin en bas de page ;
  - la page 1 n'est plus sous-comptée.
- **Faux positifs de la QA** (`c5707ca`) :
  - `skill_overflow_page_created` sur les blocs « X (suite) » de la page 1 et sur « Recette (suite) » ;
  - `pdf_fact_absent_from_source` sur le prénom du portail et sur les catégories de la taxonomie W hub (« Stack principale »).

### Ajouté
- **Backend `openrouter`** (`src/llm_backend.py`, `db067be`) :
  - appel direct à l'API OpenRouter, sortie contrainte par un schéma JSON strict (`CV_JSON_SCHEMA`) ;
  - fournisseurs filtrés : `require_parameters`, `data_collection=deny`, `zdr` en option ;
  - secours automatique `models=[principal, secours]`, une relance sur les erreurs transitoires ;
  - blocs de CV longs structurés en parallèle.
- Nouvelles catégories d'erreur non relancées : `model_config_error` et `worker_internal_error`.
- **OCR de secours** (`7628b1e`) : Tesseract `fra+eng` quand la couche texte manque ou est illisible ; score `text_readability` ; `needs_human_review` si même l'OCR échoue (cas Benjamin).
- **Alertes de santé Telegram** (`scripts/cv_health_alert.py`, `f4231cc`) :
  - worker arrêté, 3 échecs d'affilée, file bloquée, Supabase injoignable, test quotidien en échec ;
  - installées en cron le 03/11 : toutes les 15 min, test de bout en bout à 7h30 heure de Paris.
- **`scripts/model_bakeoff.py`** : comparaison de modèles hors prod sur le banc de CV (couverture, copie exacte, statut, durée, coût).
- **Compétences lues d'après les styles du PDF** (`visual_skills_extraction._extract_styled_skills`, `047fba2`) :
  - pour les modèles Canva à deux colonnes : titre de section, catégories en gras, puces, colonnes séparées ;
  - remplacement des compétences du modèle seulement en cas de confiance élevée.
- **Mise en page** (`c5707ca`) :
  - équilibrage des pages de suite en caractères et en hauteur ;
  - absorption des petits reliquats ;
  - protection de l'ouverture des expériences ;
  - expériences en page 2 si la page 1 déborderait.
- Variante de mise en page `grouped`, essayée quand la base passe en forçant les expériences sur leur propre page ; à score égal, la variante la plus courte gagne (`c5707ca`).
- `WHUB_SKILL_CATEGORY_TAXONOMY` : la taxonomie de catégories de compétences, partagée par le prompt et la QA (`c5707ca`).
- Alerte indicative `page_dense_but_acceptable` (`qa.ADVISORY_LAYOUT_CODES`) : seule, elle laisse le CV en ready et reste visible dans le rapport et l'événement `ready` (`7c29b13`).
- Documentation datée dans `ops/` : bancs, choix du modèle, fidélité et compétences, pagination.

### Modifié
- **Modèle en prod** : `google/gemini-2.5-flash` conservé après comparaison de 6 modèles, `anthropic/claude-haiku-5.5` en secours.
- **Seuil d'appel unique** : CV traités en un seul appel jusqu'à 40 000 caractères (`WHUB_MEDIUM_CV_SINGLE_PASS_THRESHOLD`).
- `temperature` n'est plus envoyée par défaut : les modèles à raisonnement la refusent.
- La règle « page trop vide » du renderer est alignée sur celle de la QA (≤ 46 %, ≤ 1 700 caractères).

### Connu
- Le test S4 (`test_worker_role.py::test_supabase_client_source_has_no_service_role_fallback`) reste rouge : les points de sécurité S1 à S4 sont hors périmètre pour l'instant.
- Les valeurs par défaut du code (backend `hermes`, modèle Nemotron, seuil 15 000) ne sont pas celles de la prod, qui reposent sur `.env`.
- Gemini 2.5 Flash n'a pas d'endpoint « zero data retention ».

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

[Unreleased]: https://github.com/SausageMan99/Whub-web/compare/7c29b13...HEAD
[0.2.0]: https://github.com/SausageMan99/Whub-web/compare/dd61fb0...7c29b13
[0.1.0]: https://github.com/SausageMan99/Whub-web/releases/tag/v0.1.0
