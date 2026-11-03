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
- **IA** : appel direct à l'API OpenRouter avec sortie JSON contrainte par schéma. En production, le modèle principal est `google/gemini-2.5-flash` et le secours automatique `anthropic/claude-haiku-5.5`. La CLI Hermes reste disponible comme chemin de secours (`WHUB_LLM_BACKEND=hermes`).
- **PDF** : extraction avec PyMuPDF, OCR Tesseract (`fra+eng`) en secours, rendu avec ReportLab et le renderer W hub du dépôt (`workers/cv-worker/renderer/whub_cv_renderer.py`).
- **Surveillance** : script d'alerte Telegram lancé par cron (voir [Surveillance](#surveillance)).
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
│   ├── eval/                     # Cas d'évaluation et smoke tests
│   └── scripts/model_bakeoff.py  # Comparaison de modèles hors prod (banc de CV)
│
├── supabase/migrations/          # Schéma DB, RPC, RLS, statuts, policies
├── scripts/                      # Gates qualité, smoke tests, alertes de santé
│   ├── e2e_smoke.py              # Un CV de bout en bout sur la prod
│   ├── cv_smoke_battery.py       # Les 11 CV du banc sur la prod
│   └── cv_health_alert.py        # Alertes Telegram (cron)
├── cv_test_bank/                 # CV de test réels (PDF ignorés par git)
├── ops/                          # Bancs datés, décisions, comptes rendus d'incident
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

Le worker extrait le texte du PDF source avec PyMuPDF, dans l'ordre visuel des blocs (`src/extraction.py`).

Cette étape donne le texte brut qui servira à construire le CV W hub.

**OCR de secours.** La couche texte peut être absente (PDF scanné) ou illisible : certaines polices ont leurs glyphes mappés sur des codes privés, et le texte sort « chiffré » (cas Benjamin). Le worker relit alors les pages par OCR (PyMuPDF + Tesseract `fra+eng`, 300 dpi).

- **Déclenchement** : moins de 400 caractères, ou lisibilité `text_readability()` inférieure à 0,5. La lisibilité est la part de tokens qui ressemblent à des mots : un vrai CV est entre 0,85 et 0,96, le texte chiffré de Benjamin à 0,06.
- **Choix du texte** : le texte OCR n'est retenu que s'il est lisible et fait au moins la moitié du texte natif.
- **Échec** : si l'OCR ne rend pas le texte lisible non plus, la demande passe en `needs_human_review` au lieu de laisser le modèle deviner le contenu.

**Normalisations sans perte** (`_clean_extracted_text`) :

- caractères de contrôle (octets NUL…) remplacés par des espaces ;
- lignes de pied de page « CV créé sur… » / « 1/3 » retirées ;
- ligatures typographiques (« ﬁ », « ﬂ », « ﬀ »…) écrites en lettres normales ;
- puces de polices symboles (Wingdings ``, ``, ``…) et sous-puces Word extraites comme un « o » seul sur sa ligne, réécrites en « • texte » sur une seule ligne. Sans ça, toute une expérience était lue comme un seul élément (cas Yannick).

Dépendance système : paquet `tesseract-ocr-fra` sur le VPS du worker.

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

Le worker retire du texte source ce qui ne doit pas apparaître dans le CV final (`src/source_sanitizer.py`) :

- coordonnées : email, téléphone, LinkedIn, GitHub, URL, adresse dans l'en-tête ;
- lignes de plateformes ATS (Hellowork : « CV téléchargé depuis », TJM, disponibilité, prétentions…) ;
- libellés de contact orphelins.

Règle de fidélité (03/11/2026) : **une ligne sans coordonnée est transmise telle quelle**. Le nettoyage de ponctuation (espaces avant « : » et « ; », virgules ou puces en bout de ligne) ne s'applique qu'aux lignes dont on vient de retirer une coordonnée. Avant cette règle, toutes les lignes perdaient la typographie française, leurs virgules finales et leurs puces.

Les noms techniques en `.net` (`ASP.NET`, `ADO.NET`, `VB.NET`, `React.NET`…) ne sont pas des noms de domaine : ils sont conservés (`is_dotnet_technical_token`). Avant, « ASP.NET MVC 5 » devenait « MVC 5 ».

Le rapport de nettoyage ne contient que des compteurs, jamais les valeurs retirées.

### Étape 6 — Structuration IA

Objectif : transformer le texte source en JSON structuré exploitable par le renderer (nom, titre, description, formations, certifications, langues, compétences, expériences), sans rien inventer.

**Appel modèle.** Le worker appelle le modèle directement via l'API OpenRouter (`WHUB_LLM_BACKEND=openrouter`, module `src/llm_backend.py`) :

- **Schéma strict** : la sortie JSON est contrainte par un schéma (`CV_JSON_SCHEMA`, toutes les propriétés requises), donc le modèle ne peut pas renvoyer de JSON invalide.
- **Choix du fournisseur** : `provider.require_parameters=true` (seuls les fournisseurs qui respectent le schéma), `data_collection=deny` (pas de fournisseur qui entraîne ses modèles sur les données). `zdr=true` en option (`WHUB_LLM_ZERO_DATA_RETENTION`), à laisser à `false` avec Gemini 2.5 Flash, qui n'a pas d'endpoint ZDR.
- **Modèles** : `models=[WHUB_PRIMARY_MODEL, WHUB_FALLBACK_MODEL]`. OpenRouter bascule automatiquement sur le secours si le principal est indisponible.
- **Erreurs** :
  - une relance sur les erreurs 408/429/5xx et les erreurs réseau ;
  - un délai dépassé est classé `model_timeout` ;
  - une réponse tronquée (`finish_reason=length`) est une erreur ;
  - une clé absente ou refusée (401/402/403/404) est classée `model_config_error`, sans relance.
- **Paramètres** : pas de `temperature` envoyée par défaut, car les modèles à raisonnement (Haiku 5.5, GPT-6) la refusent. Chaque appel est journalisé avec le modèle, le fournisseur, les tokens et le coût.

**Choix du modèle (02-03/11/2026).** Six modèles ont été comparés sur les 11 CV du banc avec `scripts/model_bakeoff.py`, sur deux critères :

- la **couverture** : part des lignes du CV source retrouvées telles quelles ;
- la **copie exacte** : part des phrases d'expérience qui sont un extrait mot pour mot.

Gemini 2.5 Flash est retenu : meilleure couverture en un seul appel, 2,5 fois plus rapide que Haiku, copie exacte à 0,99–1,0 une fois les nettoyeurs corrigés. Détail : [`ops/model-bakeoff-2026-11-02.md`](ops/model-bakeoff-2026-11-02.md).

**Un appel ou des blocs.** Jusqu'à `WHUB_MEDIUM_CV_SINGLE_PASS_THRESHOLD` caractères (40 000 en prod), le CV part en **un seul appel**. Au-delà, il est découpé en blocs structurés en parallèle (`WHUB_LONG_CV_BLOCK_PARALLELISM`, 4 par défaut), dont l'ordre est conservé. Le découpage séparait parfois une expérience de ses missions (cas Amina, en échec avec tous les modèles), d'où le seuil relevé. À l'assemblage :

- les langues et certifications de tous les blocs sont fusionnées sans doublon (elles étaient perdues) ;
- une expérience réduite à son en-tête est recollée au bloc de missions qui la suit.

**Chemin de secours Hermes.** L'ancien chemin `hermes chat` reste disponible avec `WHUB_LLM_BACKEND=hermes` (`--source tool`). Il dépend de la CLI Hermes, qui change à chaque mise à jour : c'est Hermes v0.22, refusant l'ancienne valeur `--source whub-cv-worker`, qui a cassé la production du 16 au 30/10/2026.

À ce stade, la règle importante est : l'IA structure, elle ne doit pas inventer.

### Étape 6 bis — Compétences : le CV source fait foi

Après la structuration, `src/visual_skills_extraction.py` relit la section Compétences **directement dans le PDF source**. Si la lecture est fiable, elle remplace les compétences proposées par le modèle (`_source_overrides.skills` dans le JSON).

Deux lecteurs, le premier qui est fiable gagne :

1. **Titres connus** (cas Omar / Ezzoubir) : une liste de titres de catégories reconnus.
2. **Styles du PDF** (03/11/2026), pour les modèles Canva à deux colonnes (7 des 11 CV du banc) :
   - **la section** : le grand titre « C O M P É T E N C E S … » (taille ≥ 1,3 × le corps du texte) ;
   - **les colonnes** : chaque ligne appartient au titre de section de sa colonne, donc la colonne « Formations » de droite ne se mélange plus aux compétences ;
   - **les catégories** : lignes en **gras** (un titre sur deux lignes est recollé) ;
   - **les compétences** : les puces « • », avec leurs lignes de suite.

   Une puce reste entière telle que le candidat l'a écrite (« CRM (PEGA, Salesforce) : audit, migration des données, plan de décommissionnement »). Elle n'est découpée que si c'est une vraie liste d'outils (« Python, Java, Next.js » : au moins 3 morceaux, ou 2 mots isolés, sans mot de liaison ni « : »). Les catégories hors compétences (langues, loisirs, réseaux sociaux, certifications) sont écartées, et « X (suite) » est fusionnée avec « X ».

**Garde-fous** : le remplacement efface les compétences du modèle, donc dans le moindre doute, on les garde :

- section non fermée par un autre titre (elle pourrait continuer page suivante) ;
- lignes sans catégorie ;
- moins de 2 catégories ou de 6 éléments ;
- élément de plus de 120 caractères ;
- fragment de phrase coupée (« risques. Data & Cloud: AWS »).

Les compétences que le modèle ajoutait depuis le texte des missions (outils cités dans une expérience) n'apparaissent plus dans la section Compétences, mais elles restent dans les missions, copiées mot pour mot.

Le parseur de secours `src/skills_intelligence.py`, utilisé quand aucun des deux lecteurs n'est fiable :

- ne coupe plus aux virgules entre parenthèses (« Méthodologies agiles (certifiée PSPO) ») ;
- reconnaît les titres en lettres espacées comme fin de section.

Détail : [`ops/cv-fidelity-qa-and-skills-2026-11-03.md`](ops/cv-fidelity-qa-and-skills-2026-11-03.md).

### Étape 7 — Contrôles de sécurité et fidélité

**Nettoyage du JSON produit** (`sanitize_contact_in_json`, `sanitize_identity_terms_in_json`) : les coordonnées et le nom de famille du candidat sont retirés du JSON. Depuis le 03/11/2026, seules les chaînes qui contiennent **vraiment** une coordonnée (email, téléphone, URL, profil LinkedIn/GitHub) ou le nom interdit sont retouchées. Avant, les mots « LinkedIn », « contact » ou « email » étaient effacés de toutes les phrases : « campagnes LinkedIn Ads » devenait « campagnes Ads ».

**Contrôle de fidélité** (`validate_source_fidelity`) : il compare le JSON au texte source nettoyé.

- **Bloquants** (`failed`, catégorie `source_fidelity`) : coordonnée ou identité interdite, en-tête d'expérience sans contenu, structure incohérente.
- **Alertes douces** (`_fidelity_soft_warnings`) : elles envoient le CV en `draft_ready` pour relecture humaine.
  - `experience_content_rewritten_or_absent_from_source` : une phrase d'expérience qui n'est pas un copier-coller de la source ;
  - `source_coverage_missing_experience_item` : une mission de la source absente du CV ;
  - `source_coverage_missing_section` : une section métier absente (réalisations, certifications, langues…) ;
  - `synthetic_technical_environment` : un titre « Environnement technique » inventé ;
  - `title_absent_from_source`, `company_highlight_absent_from_source`…

**Contrôle de couverture des expériences** (`extract_source_experience_coverage_items`) : il relève chaque mission de la source sous les titres « Missions », « Réalisations », « Livrables », etc. Depuis le 03/11/2026, il ne prend plus pour des missions les lignes de mise en page des PDF :

| Ligne de mise en page | Traitement |
|---|---|
| une plage de dates seule (« 07/2022 – 01/2024 », « De mai 2022 à août 2024 ») | ouvre une nouvelle expérience ; la ligne suivante (poste/entreprise) est son en-tête |
| le prénom du candidat seul sur une ligne | en-tête de page : le prénom et le titre qui suit sont ignorés, sans couper la mission en cours |
| un titre en lettres espacées (« D E S C R I P T I O N ») | ferme la section (colonne latérale) |
| « Missions (suite) », « Autres — suite » | rouvrent la section |
| « Environnement fonctionnel : … » | commence un nouvel élément |

Une mission vraiment supprimée reste signalée : c'est testé dans `tests/test_experience_coverage_layouts.py`. Ces corrections ont supprimé les fausses alertes d'oussama, hodard et rayan. Détail : [`ops/cv-fidelity-qa-and-skills-2026-11-03.md`](ops/cv-fidelity-qa-and-skills-2026-11-03.md).

**Ce qui envoie en `needs_human_review` avant tout appel modèle** :

- texte de moins de 250 caractères ou de moins de 5 lignes ;
- profil `scanned` à moins de 500 caractères ;
- lisibilité inférieure à 0,5 après OCR.

### Étape 8 — Mise en page

Le package `src/layout/` (point d'entrée `run_layout`) rend le PDF en une ou deux variantes et garde la meilleure :

1. **Variante `base`** : options issues de `build_layout_packing_options`. Un gros CV (plus de 8 expériences, ou plus de 120 unités de contenu, ou une expérience de plus de 30 unités) a ses expériences forcées sur leur propre page.
2. **Seconde variante**, une seule au maximum :
   - `layout_retry` si la base a une alerte purement de mise en page (densité, page vide, saut de page) ;
   - `grouped` (03/11/2026) si la base **passe** mais force les expériences sur de nouvelles pages : on essaie aussi la version regroupée.
3. **Sélection** (`select_best_layout_variant`) : meilleur score de « goût humain », puis statut `passed`, puis **le moins de pages**. Noel : 10 pages au lieu de 12.

Le contenu n'est jamais modifié par la mise en page (`assert_layout_retry_preserves_content`).

### Étape 9 — Rendu PDF

Le renderer W hub (`workers/cv-worker/renderer/whub_cv_renderer.py`, lancé en sous-processus) génère un PDF à la charte W hub. Les assets sont dans `workers/cv-worker/assets/`. Il ne décide pas du contenu métier : il transforme le JSON en PDF.

- **Page 1** : nom, titre, description, compétences sur deux colonnes, colonne « Formation & Diplômes » à droite (formations, certifications, langues), puis le début des expériences.
- **Pages suivantes** : expériences en pleine largeur, prénom en en-tête.

**Règles de pagination** (03/11/2026, détail dans [`ops/cv-pagination-2026-11-03.md`](ops/cv-pagination-2026-11-03.md)) :

- **Anti-crowding** : une page s'arrête vers `page_dense_char_threshold` caractères (2 850), en comptant **tout** le texte de la page comme la QA (description, compétences, colonne latérale comprises). Une puce ne fait jamais franchir la ligne QA des 3 000 caractères.
- **Équilibrage des pages de suite** : à chaque nouvelle page, le renderer estime le texte d'expériences restant, en caractères **et** en hauteur. Si la dernière page ne recevrait qu'un reliquat, le reste est réparti également sur les pages nécessaires. Sinon les pages sont remplies normalement, pour ne pas ajouter de page.
- **Reliquat** : un reste de moins de 450 caractères qui tient physiquement reste sur la page courante.
- **Ouverture d'expérience** : la date, le poste et la première section restent ensemble, sans coupure de densité entre eux. Si la première section fait moins de 120 caractères (« Systèmes : macOS… »), la section suivante en fait partie. Une ouverture qui ne tient pas en bas de page passe entière à la page suivante.
- **Page 1 surchargée** : si les compétences, la colonne latérale et l'ouverture de la première expérience dépasseraient la ligne QA, les expériences commencent en page 2.
- **Page « trop vide »** : même définition que la QA (≤ 46 % de hauteur et ≤ 1 700 caractères d'expériences).
- **Compétences** : une catégorie de plus de 8 éléments ou 470 caractères est répartie en blocs « X (suite) » dans les colonnes. Seul ce qui ne tient pas en page 1 part sur une page « Compétences techniques (suite) ».

### Étape 10 — QA du PDF et décision ready / draft_ready

`src/qa.py::run_qa` inspecte le PDF rendu :

- **Sécurité** : coordonnées, glyphes cassés, texte hors marge, logo et filigrane présents.
- **Intégrité du contenu** :
  - tout fait du JSON est dans le PDF ;
  - les lieux de mission et les sections métier de la source sont dans le PDF ;
  - tout fait du PDF est dans la source. Exceptions autorisées : les libellés du gabarit, le **prénom du portail** et la **taxonomie de catégories W hub** que le prompt impose (`WHUB_SKILL_CATEGORY_TAXONOMY`, partagée par le prompt et la QA).
- **Mise en page** (`find_layout_issues`) : page trop dense ou trop vide, dernière page clairsemée, titre d'expérience orphelin, page de compétences en débordement, bloc de compétences trop long…

La décision est prise par `classify_qa_report` (voir [Règles ready / draft_ready](#règles-ready--draft_ready)).

### Étape 11 — Sauvegarde de la version

Quand une version est produite, le worker sauvegarde :

- le JSON structuré dans `cv-renderer-inputs` ;
- le PDF final dans `cv-finals` ;
- le rapport QA dans `cv-artifacts` ;
- une ligne dans `cv_versions` ;
- le lien vers la version courante dans `cv_requests.current_version_id`.

`save_version` refuse les incohérences :

- `ready` exige `qa_report.passed = true` ;
- `draft_ready` exige `qa_report.passed != true`.

Quand le worker rétrograde en draft un CV dont la QA est passée (alertes de fidélité douces, révision de mise en page non vérifiée), il marque le rapport avec `passed: false` et `draft_override_reason` (`fidelity_soft_warnings`, `layout_revision_unverified`). Avant ce correctif du 02/11/2026, la version était rejetée et la demande finissait en échec (cas Heidi).

### Étape 12 — Événements

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

## Règles ready / draft_ready

Un PDF généré finit dans l'un de ces états. La règle vit dans `src/qa.py::classify_qa_report` et `src/main.py::process_job` :

| Situation | Statut |
|---|---|
| aucune alerte | `ready` |
| seule alerte : `page_dense_but_acceptable` (alerte **indicative**, `qa.ADVISORY_LAYOUT_CODES`, décision du 03/11/2026) | `ready` ; l'alerte reste visible dans le rapport, dans l'événement `ready` et dans le score |
| alerte de mise en page connue (`SOFT_LAYOUT_CODES` : page trop dense ou trop vide, dernière page clairsemée, titre orphelin, débordement de compétences…) | `draft_ready` |
| alerte de fidélité douce (reformulation, mission ou section absente…) | `draft_ready` (`draft_override_reason=fidelity_soft_warnings`) |
| révision de mise en page dont l'amélioration n'est pas vérifiée | `draft_ready` (`draft_override_reason=layout_revision_unverified`) |
| problème d'intégrité du contenu dans le PDF sans alerte de mise en page | `failed` / `qa_failed`, sauf si `run_layout` peut le livrer en draft (`_draft_ready_for_layout_hard_failure`) |
| coordonnée dans le PDF, logo ou filigrane absent, PDF vide, code de mise en page inconnu | `failed` / `qa_failed` |
| erreur bloquante de fidélité, de sécurité ou de modèle à la structuration | `failed` (voir [Catégories d'erreurs](#9-catégories-derreurs-cf-classify_structuring_error)) |

`draft_ready` n'est pas un échec : le PDF est téléchargeable, et la relecture humaine décide. Un brouillon signale en général un vrai écart du modèle (mission reformulée, mot retiré, catégorie inventée) ou une mise en page discutable.

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

### Suite complète du worker

```bash
cd workers/cv-worker
../../.venv/bin/python -m pytest -q
```

Attendu au 03/11/2026 : 665 tests passés, 1 en échec connu (`test_worker_role.py::test_supabase_client_source_has_no_service_role_fallback`, point de sécurité S4, hors périmètre pour l'instant). Les tests qui lisent les PDF du banc (`cv_test_bank/*/input.pdf`, ignorés par git) sont sautés si ces fichiers sont absents.

### Banc de CV de test sur la prod

Les 11 CV de `cv_test_bank/` (oussama, zahia, thorez, dense, sanitize, hodard, rayan, amina, benjamin, noel, yannick) passent dans la vraie chaîne : upload, worker, QA, puis nettoyage des demandes.

```bash
python3 scripts/cv_smoke_battery.py --reset
```

```bash
python3 scripts/e2e_smoke.py --case sanitize
```

Résultats dans `scripts/cv_smoke_results.jsonl` et `/tmp/cv_smoke_battery.log`. Les demandes de test sont déposées sous `smoke/` et ignorées par les alertes de santé. Historique : [`ops/cv-smoke-baseline-2026-11-02.md`](ops/cv-smoke-baseline-2026-11-02.md) (9/11), puis le 03/11 : 11/11, dont 8 ready.

### Comparer des modèles hors prod

```bash
cd workers/cv-worker
set -a && . ../../.env && set +a
../../.venv/bin/python scripts/model_bakeoff.py run --model google/gemini-2.5-flash --out /tmp/bakeoff/gemini.jsonl
```

```bash
../../.venv/bin/python scripts/model_bakeoff.py report /tmp/bakeoff/*.jsonl
```

Même pipeline que la prod (extraction, nettoyage, structuration, compétences, mise en page, QA), sans base de données. Le rapport donne par modèle :

- le statut (ready / draft / échec) ;
- la **couverture** (lignes source retrouvées telles quelles) et la **copie exacte** (phrases d'expérience copiées mot pour mot) ;
- les alertes de mise en page, la durée et le coût.

`--cases zahia,noel` limite le banc. Variables utiles : `WHUB_LLM_ZERO_DATA_RETENTION=true` pour un modèle compatible ZDR, `WHUB_MEDIUM_CV_SINGLE_PASS_THRESHOLD` pour tester le seuil d'appel unique.

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

### Surveillance

`scripts/cv_health_alert.py` vérifie le service, les échecs consécutifs sur les vraies demandes (3 ou plus), les demandes bloquées dans la file et, avec `--smoke`, un CV de référence de bout en bout. Les alertes partent sur le canal Telegram de Hermes (`TELEGRAM_HOME_CHANNEL`), au plus une fois toutes les 6 h pour le même problème, avec un message « rétabli » au retour à la normale.

```bash
python3 scripts/cv_health_alert.py --dry-run
python3 scripts/cv_health_alert.py --test
```

Planification en place depuis le 03/11 (crontab root, bloc `# BEGIN/END whub-cv-health`) : contrôle toutes les 15 min, et `--smoke` chaque jour à 7h30 heure de Paris. Le serveur est en UTC : la ligne tourne à 5h30 et 6h30 UTC et ne s'exécute que s'il est 7h à Paris, ce qui suit le changement d'heure. Journal : `/root/.local/state/whub-cv-health.log`.

## Variables d'environnement principales

### Web

Variables typiques côté `apps/web/.env.local` ou Vercel :

- `NEXT_PUBLIC_SUPABASE_URL`
- `NEXT_PUBLIC_SUPABASE_ANON_KEY`
- `SUPABASE_SERVICE_ROLE_KEY`
- `REDIS_URL` si BullMQ est activé

### Worker

Le service systemd lit `/root/whub-cv-factory/.env` (`EnvironmentFile`), et `.env.example` en donne le modèle. **Attention** : plusieurs valeurs par défaut du code ne sont pas celles de la prod. Un `.env` complet est donc obligatoire.

| Variable | Défaut du code | Prod (03/11/2026) | Rôle |
|---|---|---|---|
| `SUPABASE_URL`, `SUPABASE_ANON_KEY` | — | renseignées | accès Supabase |
| `WORKER_DATABASE_URL` | — | rôle `whub_worker` | accès Postgres du worker |
| `WORKER_NAME` | `whub-cv-worker-01` | | verrou des demandes |
| `POLL_INTERVAL_SECONDS` / `MAX_ATTEMPTS` | `10` / `3` | | polling, tentatives |
| `WHUB_LLM_BACKEND` | `hermes` | `openrouter` | appel direct OpenRouter ou CLI Hermes |
| `OPENROUTER_API_KEY` | vide | renseignée | clé OpenRouter (absente = `model_config_error`) |
| `WHUB_PRIMARY_MODEL` | `nvidia/nemotron-3-ultra-550b-a55b:free` | `google/gemini-2.5-flash` | modèle principal |
| `WHUB_FALLBACK_MODEL` | vide | `anthropic/claude-haiku-5.5` | secours automatique OpenRouter |
| `WHUB_MEDIUM_CV_SINGLE_PASS_THRESHOLD` | `15000` | `40000` | taille max d'un CV traité en un seul appel |
| `WHUB_LONG_CV_CHAR_THRESHOLD` | `10000` | `10000` | seuil « CV long » |
| `WHUB_LONG_CV_BLOCK_PARALLELISM` | `4` | | blocs structurés en parallèle (OpenRouter) |
| `WHUB_LLM_ZERO_DATA_RETENTION` | `false` | `false` | endpoints ZDR seulement ; aucun pour Gemini 2.5 Flash |
| `WHUB_LLM_TEMPERATURE` | non envoyée | | refusée par les modèles à raisonnement |
| `WHUB_LLM_MAX_OUTPUT_TOKENS` | `32000` | | taille max de la réponse |
| `WHUB_LLM_REASONING_EFFORT` | vide | | `low` / `medium` / `high` si le modèle le gère |
| `WHUB_PRIMARY_PROVIDER`, `HERMES_PROFILE`, `HERMES_CLI_PATH` | `openrouter`, `default`, `hermes` | | backend `hermes` uniquement |
| `WHUB_RENDERER_PATH`, `WHUB_ASSETS_DIR`, `WHUB_FONTS_DIR` | dossiers du dépôt | | renderer, logo, filigrane, polices |

Le worker doit utiliser le rôle Postgres `whub_worker` via `WORKER_DATABASE_URL` pour les opérations DB. Le service role Supabase ne doit pas être le chemin normal du worker.

Le script d'alerte lit en plus `TELEGRAM_BOT_TOKEN` et `TELEGRAM_HOME_CHANNEL` dans `/root/.hermes/.env`.

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

### Toutes les demandes échouent avec « Le modèle de structuration a échoué »

C'est l'incident du 16 au 30/10/2026 : une mise à jour de Hermes (v0.22) refusait `--source whub-cv-worker` avec `invalid_params`. Le backend `openrouter` ne dépend plus de Hermes. Si `WHUB_LLM_BACKEND=hermes` est remis, vérifier `hermes --version` et l'argument `--source tool`.

Les erreurs de configuration du modèle sont classées `model_config_error` et ne sont pas relancées :

- `invalid_params` de Hermes ;
- clé OpenRouter absente ;
- réponse HTTP 400, 401, 402, 403 ou 404.

Après correction, relancer les demandes échouées avec la RPC `unlock_job`.

### `openrouter … 404 No endpoints found that can handle the requested parameters`

Le modèle demandé n'a pas de fournisseur compatible avec les paramètres envoyés :

- `zdr=true` avec Gemini 2.5 Flash, qui n'a pas d'endpoint ZDR ;
- une `temperature` explicite avec un modèle à raisonnement (Haiku 5.5, GPT-6).

Corriger `WHUB_LLM_ZERO_DATA_RETENTION` ou `WHUB_LLM_TEMPERATURE`.

### `draft_ready requests must carry a non-passing QA report`

Le worker essayait d'enregistrer en draft un rapport QA marqué `passed`. C'est corrigé depuis le 02/11/2026 (`_mark_qa_report_draft_override`), et l'erreur est classée `worker_internal_error`. Si elle réapparaît, un nouveau chemin de rétrogradation en draft a oublié de marquer le rapport.

### Un CV complet passe en `draft_ready` avec des alertes de couverture

Lire le message de chaque alerte dans `qa_report.quality_report.soft_warnings` / `_fidelity_soft_warnings` :

- **une vraie mission manque** : c'est un écart du modèle, à relire ;
- **l'élément cité est une ligne de mise en page du PDF source** (en-tête de page, date seule, colonne latérale…) : c'est un faux positif du contrôle de couverture. Ajouter le cas dans `tests/test_experience_coverage_layouts.py` avant de corriger `extract_source_experience_coverage_items`.

### Le texte du CV généré est « chiffré » ou vide alors que le PDF source est lisible

La police du PDF source mappe ses glyphes sur des codes privés. L'OCR de secours doit prendre le relais : vérifier que `tesseract-ocr-fra` est installé (`tesseract --list-langs`) et que le journal contient `ocr fallback … ocr_readability=…`.

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
│  ├─ extraction.py    : PyMuPDF + OCR Tesseract + normalisations     │
│  ├─ text_readability : score de lisibilité (déclenche l'OCR)        │
│  ├─ source_sanitizer : retrait contacts/liens/adresses              │
│  ├─ quality_report.py: QualityReportBuilder + classify_source_profile│
│  ├─ structuring.py   : prompt, blocs, fidélité, nettoyage du JSON   │
│  ├─ llm_backend.py   : appel OpenRouter, schéma JSON strict         │
│  ├─ visual_skills_   : compétences lues dans le PDF source          │
│  │  extraction.py                                                    │
│  ├─ skills_intelli-  : parseur de compétences de secours            │
│  │  gence.py                                                         │
│  ├─ layout/          : packing + variants (base/retry/grouped)      │
│  ├─ rendering.py     : appelle renderer/whub_cv_renderer.py         │
│  ├─ qa.py            : run_qa, classify_qa_report                   │
│  └─ storage.py       : upload input.json / final.pdf / qa.json     │
│                                                                     │
│  OpenRouter : google/gemini-2.5-flash → secours claude-haiku-5.5    │
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
layout_revision_detected     → révision « mise en page seulement » : contenu réutilisé, seul le rendu est refait
                               (payload: {comments_count, from_version_id, intent: "layout_only", routing: "renderer_only"})
layout_variant_selected      → uniquement si attempts_count > 1 (payload: {selected: base|layout_retry|grouped, attempts_count})
draft_ready  OU  ready       → fin de run (payload: {version_id, version_number, layout_warnings?, fidelity_warnings?})
```

`layout_warnings` figure dans l'événement `draft_ready`, et aussi dans l'événement `ready` quand le CV porte une alerte indicative (`page_dense_but_acceptable`).

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
hermes_structuring           (structuration, quel que soit le backend : appel modèle, blocs, fidélité, compétences)
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

Le score d'extraction démarre à 88/100, descend à 72 pour `two_column`/`risky`, à 35 pour `scanned`. Le profil contient aussi `readability`, le score de lisibilité du texte (voir l'étape 3).

`should_require_human_review` renvoie `True` dans trois cas, et la demande passe alors en `needs_human_review` sans appel LLM :

- profil scanné de moins de 500 caractères ;
- moins de 250 caractères ou moins de 5 lignes ;
- lisibilité inférieure à 0,5, même après OCR.

### 9. Catégories d'erreurs (cf. `classify_structuring_error`)

Chaque erreur est classée en une seule catégorie avec un message public safe :

```text
contact_leak                   → email/téléphone/LinkedIn/GitHub dans le JSON
identity_leak                  → nom de famille candidat dans zone interdite
source_fidelity                → reformulation, hallucination, fait absent du CV source
source_sanitization            → sanitizer a retiré trop de contenu
structuring_invalid_json       → JSON du modèle ou du renderer invalide/incomplet      (relancée)
layout_density                 → page_too_dense, page_too_sparse, overflow, orphan
renderer_asset                 → logo/watermark/asset manquant
missing_candidate_first_name   → pas de pattern Prénom NOM détectable
model_timeout                  → délai dépassé à l'appel modèle                        (relancée)
model_nonzero_exit             → le modèle a répondu en erreur                         (relancée)
model_config_error             → invalid_params Hermes, clé OpenRouter absente,
                                 HTTP 400/401/402/403/404 : configuration à corriger   (non relancée)
pre_model_subprocess_error     → échec technique avant l'appel modèle (entrée invalide)
worker_internal_error          → incohérence de statut à l'enregistrement de la version (non relancée)
transient_model_failure        → échec temporaire du modèle                            (relancée)
```

Seules les catégories de `RETRYABLE_STRUCTURING_CATEGORIES` sont relancées automatiquement. `model_config_error` et `worker_internal_error` sont testées **avant** les autres : une erreur de configuration ne doit plus se faire passer pour un échec temporaire du modèle, comme pendant l'incident d'octobre 2026.

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
  soft_warnings: [ { code, stage, page?, ... } ],  // affichés en UI ; envoient en draft_ready sauf alerte indicative
  layout_issues: [ { code, page, message } ]      // détail brut (privé, jamais affiché)
}
```

Le rapport QA brut contient aussi :

- `passed` : `true` seulement sans alerte bloquante ; une alerte indicative seule le laisse à `true` ;
- `human_taste` : score de 0 à 100, pénalités et mesures page par page (caractères, hauteur utilisée) ;
- `layout_metrics` : les mesures de chaque page ;
- `draft_override_reason` (`fidelity_soft_warnings`, `layout_revision_unverified`) quand le worker a rétrogradé une QA passée en draft.

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
8. Redémarrer le worker si nécessaire (`systemctl restart whub-cv-worker`).
9. Lancer le banc complet : `python3 scripts/cv_smoke_battery.py --reset` (11/11 attendus).
10. Vérifier `cv_requests`, `cv_events`, `cv_versions` et `journalctl`.

Pour un changement de modèle, de prompt, de nettoyage ou de contrôle de fidélité, comparer d'abord hors prod avec `scripts/model_bakeoff.py` : couverture et copie exacte, avant/après.

Pour un changement de mise en page, refaire le rendu des mêmes JSON avant/après. La sortie du modèle varie d'un appel à l'autre, et seul un rendu sur données identiques isole l'effet du changement.

## État de maturité

Le projet est fonctionnel et repassé en service le 02/11/2026 après l'incident d'octobre. Il doit rester considéré comme un outil en stabilisation.

État au 03/11/2026 :

- **Banc prod** : 11/11 CV générés, dont 8 en ready, sans aucune alerte de pagination.
- **Brouillons restants** : ce sont de vrais écarts du modèle, que la relecture humaine doit voir (mission reformulée, mot retiré, section manquante).
- **Fidélité mesurée** : couverture du CV source 0,82, copie exacte des expériences 0,999 (Gemini 2.5 Flash, 11 CV).
- **Surveillance** : alertes Telegram toutes les 15 min et test de bout en bout quotidien.

Points ouverts :

1. **Sécurité** : les points S1 à S4 de `AUDIT_ARCHITECTURE.md` sont volontairement hors périmètre pour l'instant. Le test S4 (`test_worker_role.py`) reste rouge.
2. **Défauts du code** : ils ne correspondent pas à la prod (backend `hermes`, modèle Nemotron, seuil 15 000) ; la prod repose sur `.env`.
3. **Données** : Gemini 2.5 Flash n'a pas d'endpoint « zero data retention ». Les fournisseurs n'entraînent pas leurs modèles sur les CV (`data_collection=deny`), mais ils peuvent les conserver.
4. **Annexes de compétences sans titre** (cas Yannick) : elles restent lues comme des missions par le contrôle de couverture.
5. **Code en double** : `src/layout_variants.py`, `layout_intelligence.py`, `layout_retry.py` et `layout_packing.py` sont d'anciennes copies de `src/layout/`. La prod passe par `src/layout/` (`run_layout`), avec une exception : `rendering.py` importe encore `assert_layout_retry_preserves_content` depuis `src/layout_retry.py`. Une modification de la mise en page se fait dans `src/layout/`, et des tests historiques visent encore les anciennes copies.

## Historique des évolutions récentes

| Date | Changement | Détail |
|---|---|---|
| 16–30/10/2026 | Panne : toutes les demandes en échec (Hermes v0.22 refuse `--source whub-cv-worker`) | [`.hermes/plans/2026-11-02_140000-remise-en-service-et-choix-modele.md`](.hermes/plans/2026-11-02_140000-remise-en-service-et-choix-modele.md) |
| 02/11 | Remise en service (`--source tool`), 9 demandes bloquées récupérées ; erreurs de configuration classées à part | idem |
| 02/11 | Correctif : un draft issu d'une QA passée n'est plus rejeté (cas Heidi) ; commentaires de compétences routés vers une révision de contenu | [`ops/cv-smoke-baseline-2026-11-02.md`](ops/cv-smoke-baseline-2026-11-02.md) |
| 02/11 | Appel direct OpenRouter avec schéma JSON strict ; blocs en parallèle | étape 6 |
| 02/11 | OCR de secours pour les PDF illisibles (cas Benjamin) | étape 3 |
| 02/11 | Alertes Telegram de santé (installées en cron le 03/11) | [Surveillance](#surveillance) |
| 02–03/11 | Comparaison de 6 modèles : Gemini 2.5 Flash conservé, Haiku 5.5 en secours, un seul appel jusqu'à 40 000 caractères | [`ops/model-bakeoff-2026-11-02.md`](ops/model-bakeoff-2026-11-02.md) |
| 03/11 | Les nettoyeurs n'altèrent plus le texte (ASP.NET, ponctuation, « LinkedIn Ads ») ; ligatures et puces Wingdings normalisées | étapes 3, 5, 7 |
| 03/11 | Fin des fausses alertes de couverture (en-têtes, colonne latérale, « (suite) ») ; compétences lues d'après les styles du PDF | [`ops/cv-fidelity-qa-and-skills-2026-11-03.md`](ops/cv-fidelity-qa-and-skills-2026-11-03.md) |
| 03/11 | Pagination équilibrée, ouverture d'expérience protégée, variante regroupée, moins de pages à score égal ; faux positifs QA retirés ; page dense acceptable seule = ready | [`ops/cv-pagination-2026-11-03.md`](ops/cv-pagination-2026-11-03.md) |

Le détail par version figure dans [`CHANGELOG.md`](CHANGELOG.md).

## Explication courte pour non-technique

CV Factory est un outil interne W hub qui prend un CV candidat brut, extrait les informations importantes, les remet dans un modèle W hub, génère un PDF propre et vérifie automatiquement que le contenu reste fidèle au CV original.

L'équipe peut suivre l'avancement, télécharger le CV généré, demander une correction ou relancer une demande si le système détecte un problème.

Le but est de produire des CV W hub plus vite, sans perdre la fiabilité ni inventer d'informations candidat.
