# W hub CV Factory — audit logs génération CV et plan de correction

> **Pour Hermes :** utiliser `subagent-driven-development` si ce plan est exécuté en autonome, avec une tâche d’implémentation puis une revue CTO/QA avant toute mise en production.

**Objectif :** fiabiliser le générateur W hub pour transformer un CV source en PDF W hub fidèle, sans contact candidat, sans réécriture non autorisée, avec une mise en page propre.

**Architecture :** le problème principal se situe dans la couche worker/structuration/QA, pas dans le principe du rendu. Le pipeline doit rester strict sur les contacts et la fidélité source, mais moins naïf sur les faux positifs d’identité, les entêtes PDF et les mots métier.

**Stack :** Python worker, Supabase `cv_requests` / `cv_events`, renderer PDF W hub, tests pytest, service systemd `whub-cv-worker.service`.

---

## 1. Audit structuré

### 1.1 État vérifié

Le service `whub-cv-worker.service` est actif et poll Supabase correctement. Le dernier état observé sur les demandes récentes montre un produit partiellement fonctionnel : plusieurs CV atteignent `ready` ou `draft_ready`, mais il reste un volume non négligeable de `failed` et quelques `qa_failed`.

Le repo local n’est pas propre : `workers/cv-worker/src/config.py` et `workers/cv-worker/src/structuring.py` contiennent des modifications non committées. Ces modifications semblent liées à l’ajout d’un fallback modèle et à la correction de faux positifs d’identité.

Les contrôles techniques observés : `py_compile` passe sur les fichiers worker critiques, `git diff --check` passe, mais `PYTHONPATH=. pytest -q tests/test_structuring.py` échoue sur 2 tests liés au fallback Hermes, avec 85 tests passés.

### 1.2 Point fort produit

Le pipeline a la bonne promesse : il ne cherche pas à réécrire le CV, il extrait, structure, protège les données candidat, puis rend en charte W hub. La présence de gardes QA sur contacts, identité, densité de page, couverture source et glyphes est saine. Sans ces gardes, le produit sortirait vite des CV “jolis” mais infidèles ou dangereux.

Les `ready` et `draft_ready` prouvent que la chaîne complète peut fonctionner. Les artefacts de smoke Sprint 3 montrent aussi des cas avec QA passée, couverture source complète et absence de contacts.

### 1.3 Point faible principal

La validation d’identité est trop agressive. Elle confond parfois un vrai nom de famille avec des entêtes ou des mots métier. Les logs montrent des blocages sur `COMPETENCES`, `gestion`, `SQL`, et des entêtes de type `DOSSIER DE COMPETENCES | Prénom NOM Page 1/5`. Ce sont des faux positifs qui bloquent des CV valides.

Ce défaut est grave parce qu’il casse l’expérience utilisateur : l’utilisateur interne ne comprend pas pourquoi un CV échoue alors que le contenu est exploitable. Mais il ne faut pas supprimer la garde ; il faut la rendre plus intelligente.

### 1.4 Deuxième faiblesse

Le fallback modèle est intégré de manière encore fragile. L’ajout de `WHUB_FALLBACK_MODEL` a provoqué un incident Pydantic `extra_forbidden` avant correction de `Settings`. Les tests actuels échouent parce que le fallback réel est appelé dans des tests qui injectent un runner mocké. Le fallback doit être injectable et testable sans lancer Hermes.

### 1.5 Troisième faiblesse

La source fidelity QA détecte parfois des vrais problèmes, mais elle mélange plusieurs types de défauts : fuite d’identité, section technique synthétique, fait PDF absent de la source, densité layout. Ces erreurs sont utiles, mais pas assez classées pour l’utilisateur final. Pour W hub, il faut distinguer : sécurité bloquante, fidélité bloquante, structuration récupérable, layout soft warning.

### 1.6 Problèmes réels confirmés par les logs

Un vrai contact `@` a été bloqué dans `SABRINA TRABELSI.pdf`. Cette garde doit rester stricte, avec exception uniquement pour des noms de projet type `Th@Bot`, déjà couverts par le code.

Deux `qa_failed` historiques montrent de vrais défauts : une sortie avec des faits PDF absents de la source, et une sortie trop dense sur une page. Ces deux cas justifient de garder une QA forte.

### 1.7 Jugement stratégique

Le produit est dans une phase normale d’industrialisation : le moteur sait produire, mais la fiabilité n’est pas encore suffisante pour remplacer sereinement le travail manuel. Le risque n’est pas technique pur ; le risque est opérationnel : si les alternants W hub doivent relancer, comprendre les erreurs ou demander à Clément, le gain de temps disparaît.

La cible doit être : 80–90 % des CV standards sortent en `ready` ou `draft_ready`, les vrais blocages sont lisibles, et les faux positifs d’identité deviennent rares.

---

## 2. Plan de correction priorisé

### Phase 0 — Stabiliser l’état avant correction

**Objectif :** partir d’un état connu et éviter de corriger par-dessus du code ambigu.

**Fichiers :**
- Inspecter : `workers/cv-worker/src/config.py`
- Inspecter : `workers/cv-worker/src/structuring.py`
- Inspecter : `workers/cv-worker/tests/test_structuring.py`

**Actions :**
1. Faire un `git diff` complet des deux fichiers modifiés.
2. Séparer ce qui est déjà bon de ce qui est expérimental.
3. Ne pas déployer tant que les tests structuring ne passent pas.
4. Documenter les deux échecs tests actuels comme dette fallback, pas comme dette renderer.

**Vérification :**
```bash
git status --short --branch
git diff --check
python -m py_compile src/config.py src/structuring.py src/main.py
PYTHONPATH=. pytest -q tests/test_structuring.py
```

### Phase 1 — Corriger le fallback Hermes proprement

**Objectif :** permettre un fallback GPT/ autre modèle sans casser les tests ni masquer les erreurs primaires.

**Fichiers :**
- Modifier : `workers/cv-worker/src/structuring.py`
- Modifier : `workers/cv-worker/tests/test_structuring.py`

**Actions :**
1. Ajouter un paramètre optionnel `fallback_runner` à `build_whub_json`.
2. En test, injecter un fallback mocké au lieu d’appeler `_fallback_hermes_runner` réel.
3. Si le fallback n’est pas configuré, ne pas écraser l’erreur primaire par `No fallback model configured` ou par une erreur Hermes runtime non liée.
4. Ajouter un test : primaire échoue, fallback absent, l’erreur primaire remonte.
5. Ajouter un test : primaire retourne JSON avec contact, fallback retourne JSON propre, le résultat final passe.
6. Ajouter un test : primaire et fallback échouent, l’erreur finale mentionne les deux tentatives de manière lisible.

**Vérification :**
```bash
PYTHONPATH=. pytest -q tests/test_structuring.py::TestBuildWHubJson
PYTHONPATH=. pytest -q tests/test_structuring.py
```

### Phase 2 — Durcir l’inférence d’identité sans faux positifs

**Objectif :** bloquer les vrais noms de famille, pas les mots métier ni les entêtes PDF.

**Fichiers :**
- Modifier : `workers/cv-worker/src/structuring.py`
- Modifier : `workers/cv-worker/tests/test_structuring.py`

**Actions :**
1. Garder le principe : si `candidate_first_name` est connu, ne chercher l’identité que sur les lignes proches contenant ce prénom.
2. Exclure systématiquement les tokens documentaires : `DOSSIER`, `COMPETENCES`, `CV`, `CURRICULUM`, `VITAE`, `PAGE`, sauf cas réel de nom comme `Jean Page`.
3. Si `candidate_first_name` est absent, ne pas scanner tout le CV ; limiter à la zone d’entête et refuser les lignes métier.
4. Ajouter des tests de non-régression pour `SQL Server`, `Gestion de bases de données`, `DATA Analyst`, `Université`, `langue`, `Niveau`.
5. Ajouter des tests qui gardent les vrais surnoms : `Nicolas GONZALEZ`, `Rachid AGOUARANE`, `Jean Page`.
6. Ajouter un test LinkedIn/Profile PDF où le nom complet apparaît dans le résumé : le surnom doit être interdit, mais la ville et le titre ne doivent pas devenir des forbidden terms.

**Vérification :**
```bash
PYTHONPATH=. pytest -q tests/test_structuring.py -k "identity or forbidden or source_fidelity"
PYTHONPATH=. pytest -q tests/test_structuring.py
```

### Phase 3 — Clarifier la taxonomie d’erreurs

**Objectif :** que l’interface et les logs expliquent le vrai type de problème.

**Fichiers :**
- Modifier : `workers/cv-worker/src/structuring.py`
- Modifier : `workers/cv-worker/src/qa.py`
- Modifier si nécessaire : code web d’affichage statut erreur

**Actions :**
1. Classer les erreurs en catégories : `contact_leak`, `identity_leak`, `source_fidelity`, `structuring_invalid_json`, `layout_density`, `renderer_asset`, `transient_model_failure`.
2. Dans `last_error`, garder le message court et stocker les détails dans `cv_events.payload`.
3. Pour les faux positifs potentiels d’identité, ajouter le contexte extrait mais ne jamais imprimer de secrets.
4. Côté UX, afficher une formulation actionnable : “Coordonnée détectée”, “Nom candidat exposé”, “Contenu modifié ou absent”, “Mise en page à vérifier”.

**Vérification :**
Créer 4 fixtures locales : contact leak, surname leak, faux positif métier, page dense. Vérifier que chaque cas sort la bonne catégorie.

### Phase 4 — Relancer les demandes échouées récupérables

**Objectif :** ne pas laisser des jobs en `failed` après correction.

**Actions :**
1. Identifier les demandes échouées par faux positif déjà corrigé : Rachid / `COMPETENCES`, Malik / `gestion` ou `SQL`, Nicolas / `GONZALEZ` si la sortie expose réellement le nom dans le JSON.
2. Ne relancer que les demandes dont la cause est comprise.
3. Garder les vrais contacts bloqués en `failed` tant que la structuration ne retire pas le contact.
4. Documenter chaque relance dans `cv_events`.

**Vérification :**
Après relance, vérifier statut final `ready` ou `draft_ready`, QA report, absence de contact et absence de nom de famille.

### Phase 5 — Vérifier la qualité PDF, pas seulement le statut

**Objectif :** éviter les faux verts.

**Actions :**
1. Pour au moins 5 CV réels, extraire le texte source, le JSON renderer et le PDF final.
2. Vérifier couverture source : aucune section business-relevant absente sans raison autorisée.
3. Vérifier absence contact / surname dans le PDF extrait.
4. Vérifier densité pages : pas de page trop dense, pas de dernière page quasi vide, pas de titre d’expérience orphelin.
5. Faire une inspection visuelle rapide des premières et dernières pages.

**Vérification :**
Produire un evidence ledger local avec : request id, statut, pages, contact hits, source coverage, layout issues, verdict humain.

### Phase 6 — Release propre

**Objectif :** passer d’un correctif local à une version durable.

**Actions :**
1. Committer uniquement les fichiers worker concernés.
2. Ne pas embarquer `.hermes/`, `artifacts/` ou changements non liés.
3. Redémarrer `whub-cv-worker.service` uniquement après tests verts.
4. Vérifier logs startup preflight.
5. Lancer un smoke réel sur un CV connu.

**Vérification :**
```bash
git status --short
git diff --check
PYTHONPATH=. pytest -q tests/test_structuring.py
python -m py_compile src/config.py src/structuring.py src/main.py
sudo systemctl restart whub-cv-worker.service
systemctl status whub-cv-worker.service --no-pager --full
journalctl -u whub-cv-worker.service --since '10 minutes ago' --no-pager -o short-iso
```

---

## 3. Ordre recommandé

Ne pas commencer par le rendu PDF. Le rendu est moins coupable que la structuration/QA.

Priorité 1 : réparer fallback + tests.
Priorité 2 : corriger identité/faux positifs.
Priorité 3 : améliorer taxonomie d’erreurs.
Priorité 4 : relancer les jobs récupérables.
Priorité 5 : smoke multi-CV avec evidence ledger.
Priorité 6 : commit + restart worker + vérification prod.

---

## 4. Critère de réussite

Le correctif est acceptable seulement si :

1. Les tests structuring passent.
2. Les vrais contacts restent bloqués.
3. Les mots métier comme `SQL`, `gestion`, `COMPETENCES` ne bloquent plus seuls.
4. Les vrais noms de famille restent interdits dans le JSON/PDF.
5. Un CV source réel passe en `ready` ou `draft_ready` avec QA vérifiée.
6. Le worker prod tourne sans boucle de restart après déploiement.
