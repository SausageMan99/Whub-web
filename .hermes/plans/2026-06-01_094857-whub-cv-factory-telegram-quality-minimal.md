# Plan — rapprocher le portail W hub CV Factory du résultat Telegram sans over-engineering

## Objectif

Rendre le portail W hub CV Factory fiable sur les CV standards comme celui de Rachid, avec une qualité proche du traitement manuel Telegram, sans transformer le produit en usine agentique complexe.

Le résultat attendu n’est pas “Hermes Telegram dans une page web”. Le résultat attendu est un worker simple et maintenable qui :

- génère un PDF W hub fidèle dans 80–90% des cas internes normaux ;
- ne bloque pas sur des faux positifs évidents ;
- continue à bloquer les vraies fuites de coordonnées / identité candidat ;
- produit des erreurs compréhensibles quand il bloque ;
- est protégé par des tests sur vrais cas de CV.

## Contexte actuel

Cas analysé : demande `d00d4f07-755c-464a-a26b-babec69a18f8`, fichier `Dossier de competences-Rachid - MAJ_28052026.pdf`.

Le worker a bien :

- claim la demande ;
- téléchargé le PDF source ;
- extrait environ `12 419` caractères ;
- lancé la structuration Hermes en mode `single`, durée environ `70.60s`, retour `0`.

Il a ensuite échoué en QA de fidélité avec :

```text
candidate_identity_term_exposed: COMPETENCES
```

Cause racine : `infer_forbidden_candidate_identity_terms()` a pris la ligne d’en-tête PDF :

```text
DOSSIER DE COMPETENCES | Rachid AGOUARANE Page 1/5
```

pour une ligne d’identité candidat, et a donc ajouté à tort dans les termes interdits :

```text
DOSSIER, COMPETENCES, AGOUARANE, Page
```

La bonne détection aurait dû garder uniquement le vrai nom de famille `AGOUARANE`, et ignorer les mots documentaires `DOSSIER`, `COMPETENCES`, `Page`.

## Principe produit

Ne pas over-engineerer.

Le portail doit rester :

```text
Upload CV → extraction → structuration fidèle → renderer W hub → QA → ready / failed clair
```

On ajoute seulement trois capacités ciblées :

1. heuristiques d’identité plus propres ;
2. retry unique uniquement sur erreurs corrigeables ;
3. tests de non-régression sur vrais cas.

Pas de système multi-agent, pas d’interface complexe de correction, pas de 4 passes LLM systématiques, pas d’analyse visuelle IA obligatoire au premier sprint.

## Approche proposée

### 1. Corriger la détection d’identité candidat

Fichier principal :

```text
workers/cv-worker/src/structuring.py
```

Fonctions concernées :

```python
infer_forbidden_candidate_identity_terms()
_identity_tokens()
_contains_forbidden_identity_term()
validate_source_fidelity()
```

Problème actuel : si une ligne des premières lignes contient le prénom candidat et au moins deux tokens, elle peut être considérée comme identité, même si c’est un header de document.

Nouvelle logique minimale :

- ignorer les lignes documentaires avant de chercher l’identité ;
- reconnaître les patterns de headers/pieds de page :
  - `DOSSIER DE COMPETENCES`
  - `DOSSIER DE COMPÉTENCES`
  - `CV`
  - `CURRICULUM VITAE`
  - `Page 1/5`, `Page 2 sur 5`, etc.
  - lignes contenant `|` avec un titre documentaire + nom + page ;
- préférer une ligne courte contenant seulement prénom + nom, par exemple `Rachid AGOUARANE` ;
- ne jamais ajouter comme terme interdit des mots génériques documentaires.

Liste de mots à exclure des termes interdits même s’ils sont dans une ligne candidate :

```text
DOSSIER, COMPETENCES, COMPÉTENCES, CV, CURRICULUM, VITAE, PAGE, PROFIL, CONSULTANT, CONSULTANTE
```

Attention : ne pas rendre la sécurité laxiste. `AGOUARANE` doit rester interdit.

### 2. Ajouter un fallback déterministe avant de déclarer l’échec

Toujours dans :

```text
workers/cv-worker/src/structuring.py
```

But : quand `validate_source_fidelity()` détecte `candidate_identity_term_exposed`, vérifier si le terme est manifestement générique/documentaire.

Exemple :

```text
COMPETENCES
DOSSIER
PAGE
CV
```

Si oui :

- ne pas bloquer ;
- logguer un warning structuré ;
- continuer la QA avec les vrais termes interdits restants.

Ce fallback doit être très limité. Il ne doit jamais ignorer :

- nom de famille réel ;
- email ;
- téléphone ;
- LinkedIn ;
- adresse ;
- full name.

### 3. Ajouter un retry unique seulement si nécessaire

Fichiers probables :

```text
workers/cv-worker/src/main.py
workers/cv-worker/src/structuring.py
```

Ne pas créer une boucle agentique lourde.

Comportement recommandé :

- première structuration normale ;
- si échec sur une erreur classée `recoverable_structuring_error`, faire une seule tentative corrective ;
- si la deuxième tentative échoue, passer en `failed` avec une erreur claire.

Erreurs récupérables au départ :

- `candidate_identity_term_exposed` quand le terme est générique/documentaire ;
- JSON incomplet avec clé liste manquante (`formations`, `skills`, `experiences`) quand la source permet une valeur `[]` sûre ;
- éventuellement erreur de formatting JSON pur si la sortie est réparable sans changer le contenu.

Ne pas inclure dans les erreurs récupérables :

- fuite email/téléphone/LinkedIn ;
- nom de famille réel ;
- expériences manquantes massivement ;
- hallucination manifeste ;
- renderer overflow bloquant.

### 4. Créer un test de non-régression Rachid

Fichiers probables :

```text
workers/cv-worker/tests/test_structuring.py
workers/cv-worker/tests/test_qa.py
```

Ajouter un test unitaire sur la fonction d’identité avec le début de texte extrait :

```text
DOSSIER DE COMPETENCES | Rachid AGOUARANE Page 1/5

Rachid AGOUARANE
Consultant Esker | Business Analyst IT (Run/Build)
```

Assertions attendues :

```python
terms = infer_forbidden_candidate_identity_terms(source_text, "Rachid")
assert "AGOUARANE" in terms
assert "COMPETENCES" not in terms
assert "DOSSIER" not in terms
assert "Page" not in terms
```

Ajouter aussi un test de QA : une phrase contenant `compétences` ne doit pas déclencher `candidate_identity_term_exposed`.

Exemple :

```text
Contenu fidèle complet: compétences et certifications regroupées pour lisibilité.
```

Doit passer si le seul vrai terme interdit est `AGOUARANE`.

### 5. Ajouter un smoke réel contrôlé avec le PDF Rachid si possible

Idéalement, ajouter un fixture anonymisé ou utiliser le PDF source dans un dossier d’artifacts non commité si le repo ne doit pas contenir de CV réels.

Options :

- option A, plus sûre : test unitaire avec extrait texte minimal, pas le PDF complet ;
- option B, meilleure QA interne : smoke local non commité avec le vrai PDF stocké dans `artifacts/` ;
- option C, si accepté par W hub : fixture anonymisé qui reproduit exactement le header fautif.

Recommandation : commencer par option A dans les tests, option B en smoke manuel de release.

### 6. Améliorer l’observabilité sans surcharger l’UX

Fichiers probables :

```text
workers/cv-worker/src/events.py
workers/cv-worker/src/main.py
workers/cv-worker/src/structuring.py
```

Ajouter dans les logs/events, sans données sensibles :

- termes d’identité inférés ;
- ligne source utilisée pour les inférer ;
- termes ignorés car documentaires ;
- type d’échec : `identity_false_positive`, `real_identity_leak`, `contact_leak`, `source_coverage`, `renderer`.

Ne pas afficher tout ça à l’utilisateur final. Le portail peut garder un message simple, mais l’admin/debug doit permettre de comprendre vite.

## Étapes détaillées d’implémentation

### Étape 1 — Baseline read-only

Commandes de vérification avant changement :

```bash
cd /root/whub-cv-factory
python -m pytest workers/cv-worker/tests/test_structuring.py workers/cv-worker/tests/test_qa.py -q
```

Objectif : savoir si les tests actuels sont verts avant modification.

### Étape 2 — Test RED sur Rachid

Ajouter un test qui reproduit l’échec actuel dans :

```text
workers/cv-worker/tests/test_structuring.py
```

Le test doit échouer avant fix si l’ancienne logique retourne `COMPETENCES`.

### Étape 3 — Fix identité minimal

Modifier `infer_forbidden_candidate_identity_terms()` pour :

- filtrer les lignes documentaires ;
- scorer les lignes candidates ;
- préférer les lignes courtes prénom + nom ;
- exclure les tokens génériques.

Pseudo-logique :

```python
DOCUMENT_HEADER_RE = re.compile(...)
DOCUMENT_IDENTITY_STOPWORDS = {...}

def _is_document_header_line(line): ...
def _is_generic_identity_token(token): ...
def _candidate_identity_lines(source_text, allowed_first): ...
```

Ne pas refaire tout le module. Garder la modification locale.

### Étape 4 — QA non-régression

Ajouter ou adapter un test dans :

```text
workers/cv-worker/tests/test_qa.py
```

But : valider que `validate_source_fidelity()` ne bloque pas sur `compétences` quand ce mot vient d’un header, mais bloque encore sur `AGOUARANE` si présent dans le JSON.

### Étape 5 — Retry unique récupérable, seulement si le fix identité ne suffit pas

Ne pas implémenter cette étape si les cas actuels sont résolus par les heuristiques.

Si nécessaire, ajouter une exception ou un code d’erreur structuré dans `StructuringError`, puis dans `main.py` faire :

```text
try build_whub_json
except recoverable: retry once with corrective context
```

Important : cette étape est secondaire. Elle ne doit pas être le premier réflexe.

### Étape 6 — Validation complète worker

Commandes :

```bash
cd /root/whub-cv-factory/workers/cv-worker
python -m pytest tests/test_structuring.py tests/test_qa.py -q
python -m pytest tests -q
python -m py_compile src/*.py
```

Si trop long, au minimum :

```bash
python -m pytest tests/test_structuring.py tests/test_qa.py tests/test_preflight.py -q
```

### Étape 7 — Smoke Rachid hors prod

Utiliser le PDF source déjà disponible localement si présent :

```text
/root/.hermes/cache/documents/doc_1ed0dec43470_Dossier de competences-Rachid - MAJ_28052026.pdf
```

But du smoke : vérifier que la structuration ne bloque plus sur `COMPETENCES` et que le PDF final ne contient pas :

- `AGOUARANE` ;
- email ;
- téléphone ;
- LinkedIn ;
- adresse ;
- glyphes corrompus.

Ne pas pousser en prod sans accord de Clément.

## Fichiers susceptibles de changer

Prioritaires :

```text
workers/cv-worker/src/structuring.py
workers/cv-worker/tests/test_structuring.py
workers/cv-worker/tests/test_qa.py
```

Possibles mais à éviter si non nécessaires :

```text
workers/cv-worker/src/main.py
workers/cv-worker/src/events.py
workers/cv-worker/tests/test_main_layout_retry.py
```

À ne pas toucher dans ce sprint sauf nécessité explicite :

```text
apps/web/**
supabase/**
renderer/layout/**
Vercel config
systemd service
```

## Tests et validation

Validation minimale :

```bash
cd /root/whub-cv-factory/workers/cv-worker
python -m pytest tests/test_structuring.py tests/test_qa.py -q
python -m py_compile src/*.py
```

Validation recommandée :

```bash
cd /root/whub-cv-factory/workers/cv-worker
python -m pytest tests -q
```

Validation produit :

- relancer localement ou en staging un job Rachid ;
- vérifier statut `ready` ou au moins absence du faux blocage `COMPETENCES` ;
- extraire le PDF final ;
- vérifier absence de coordonnées et nom de famille ;
- vérifier présence des expériences principales.

Validation non-régression sécurité :

- test où `AGOUARANE` apparaît dans le JSON visible → doit échouer ;
- test où email/téléphone/LinkedIn apparaissent → doit échouer ;
- test où `compétences` apparaît normalement → doit passer.

## Risques et arbitrages

### Risque 1 — Trop assouplir la QA

Si on ignore trop de termes, on peut laisser passer un vrai nom de famille.

Mitigation : ignorer uniquement des stopwords documentaires, jamais les tokens extraits d’une vraie ligne `Prénom NOM`.

### Risque 2 — Ajouter un retry LLM trop tôt

Un retry systématique rend le worker plus lent, plus cher et plus difficile à debugger.

Mitigation : ne faire le retry qu’en deuxième phase, uniquement sur erreurs classées récupérables, maximum une fois.

### Risque 3 — Tests trop artificiels

Un extrait texte minimal peut rater des problèmes réels de PDF.

Mitigation : combiner test unitaire commitable + smoke manuel avec PDF réel avant release.

### Risque 4 — Confondre “même résultat que Telegram” avec “même intelligence partout”

Ce serait une erreur produit. Telegram peut gérer des cas ambigus par jugement humain/agentique. Le portail doit couvrir les cas fréquents de façon stable.

Mitigation : viser 80–90% de réussite autonome, et des échecs propres sur le reste.

## Questions ouvertes

1. Est-ce que W hub accepte de stocker quelques CVs réels en fixtures privées pour smoke tests internes, ou faut-il seulement des extraits anonymisés ?
2. Veut-on exposer un statut `draft_ready` maintenant, ou attendre d’avoir stabilisé les faux échecs ?
3. Est-ce que les utilisateurs internes doivent voir un message détaillé ou seulement “échec technique, support notifié” ?

## Décision recommandée

Implémenter d’abord uniquement :

1. correction heuristique identité/header ;
2. tests Rachid ;
3. smoke local Rachid ;
4. logs plus explicites.

Ne pas implémenter tout de suite :

- agent complet ;
- analyse visuelle IA systématique ;
- interface de correction avancée ;
- retry multi-passes ;
- refonte layout.

C’est la trajectoire la plus rentable : elle corrige le bug réel, améliore la fiabilité perçue, et garde le portail maintenable.
