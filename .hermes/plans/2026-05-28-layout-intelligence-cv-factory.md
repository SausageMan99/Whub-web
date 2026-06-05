# W hub CV Factory Layout Intelligence Acceptance Plan

> **For Hermes:** Use subagent-driven-development skill to implement this plan task-by-task.

**Goal:** Corriger le cas Oussama et les CV similaires où le PDF est techniquement généré mais pas client-ready: compétences trop longues/mal réparties, saut de page d'expérience disgracieux, manque de goût et de lisibilité.

**Architecture:** La correction doit rester factuelle et déterministe autant que possible. La structuration doit produire un JSON plus présentable sans inventer de contenu; le renderer doit décider intelligemment de la densité, du placement et des sauts de page; la QA doit bloquer les rendus visuellement amateurs, pas seulement les coordonnées/overflow.

**Tech Stack:** Python worker `workers/cv-worker`, renderer global ReportLab `/root/.hermes/scripts/whub_cv_renderer.py`, QA PyMuPDF `workers/cv-worker/src/qa.py`, tests pytest/unittest.

---

## État constaté au préflight

Repo: `/root/whub-cv-factory`.

Changements non commités existants à préserver, hors périmètre layout:
- `apps/web/app/requests/new/NewRequestForm.tsx`
- `apps/web/app/requests/new/actions.ts`
- `apps/web/app/requests/new/page.tsx`
- `apps/web/tests/upload.test.ts`

Ces changements concernent le flux `createRequest`/signed upload. Ne pas les modifier dans la suite layout, ne pas les revert, ne pas les inclure dans un commit layout.

Fichiers inspectés pour la mission:
- `workers/cv-worker/src/structuring.py`
- `/root/.hermes/scripts/whub_cv_renderer.py`
- `workers/cv-worker/src/qa.py`
- `workers/cv-worker/src/main.py`
- `workers/cv-worker/src/rendering.py`
- tests worker existants: `test_structuring.py`, `test_structuring_long_cv.py`, `test_rendering.py`, `test_renderer_overflow.py`, `test_qa.py`, `test_qa_text_overflow.py`

Checks baseline lancés:
- `python ~/.hermes/skills/user-workflows/whub-client-cv-generator/scripts/verify_whub_assets.py` → PASS.
- `python -m py_compile workers/cv-worker/src/structuring.py workers/cv-worker/src/qa.py workers/cv-worker/src/rendering.py /root/.hermes/scripts/whub_cv_renderer.py` → PASS.
- `PYTHONPATH=workers/cv-worker pytest -q workers/cv-worker/tests/test_structuring.py workers/cv-worker/tests/test_structuring_long_cv.py workers/cv-worker/tests/test_rendering.py workers/cv-worker/tests/test_renderer_overflow.py workers/cv-worker/tests/test_qa.py workers/cv-worker/tests/test_qa_text_overflow.py` → 49 passed, 1 Pydantic warning.
- `npm test` → PASS, 68 tests passed; warnings/logs attendus dans les tests auth/upload/download.

Aucun déploiement, aucun restart worker.

---

## Root cause produit probable

Le pipeline actuel a déjà de bonnes bases: contact guard, long-CV multi-pass, condensation standard, renderer avec anti-overflow basique, continuation de longues compétences, QA overflow. Le problème Oussama est plus haut niveau: le système ne sait pas encore juger si le PDF est élégant et lisible.

Points faibles précis:

1. `structuring.py:_group_long_skills` transforme une catégorie de plus de 6 items en un seul item joint par `; `. C'est factuellement safe mais visuellement mauvais: le renderer le traite comme un paragraphe/bullet énorme, peu scannable, difficile à équilibrer et susceptible de créer un mur de texte.

2. `/root/.hermes/scripts/whub_cv_renderer.py:287-329` répartit les catégories de compétences par alternance `skills[::2]` / `skills[1::2]`, pas par hauteur réelle. Une colonne peut devenir dense pendant que l'autre respire; c'est visible sur les CV où une catégorie est beaucoup plus longue.

3. `/root/.hermes/scripts/whub_cv_renderer.py:339-350` affiche les compétences overflow en full width avec bullet list mais sans vraie stratégie de densité/colonnes. Pour un CV type Oussama, la page de suite peut devenir un inventaire lourd avant même les expériences.

4. `/root/.hermes/scripts/whub_cv_renderer.py:406-414` rend la première expérience directement sur page 1 sans utiliser `render_experience`. Donc l'expérience d'ouverture n'a pas le même garde-fou anti-orphan que les suivantes: date/rôle/heading peuvent se retrouver mal placés si les compétences ont mangé l'espace.

5. `qa.py` bloque contacts, glyphes, assets et texte hors marge, mais ne bloque pas les défauts de goût: titre d'expérience isolé en bas de page, page finale quasi vide, compétences démesurées en page 1, déséquilibre extrême des colonnes, page 1 sans expérience utile alors que le lecteur s'attend à voir la proposition de valeur rapidement.

---

## Acceptance criteria non négociables

### Contenu / factualité

- Le JSON final garde `name` en prénom seul, idéalement fourni par `candidate_first_name`.
- Aucune coordonnée candidat: email, téléphone, LinkedIn, URL, GitHub profil, adresse.
- Aucune invention: pas de dates, clients, titres, outils, diplômes ou réalisations absents du CV source.
- Les technologies exactes restent présentes, mais peuvent être regroupées et dédupliquées pour lisibilité.
- Les expériences récentes restent détaillées; les expériences anciennes peuvent être condensées seulement avec mention explicite `Synthèse mission` selon la politique existante.

### Compétences

- Une catégorie de compétences très longue ne doit jamais devenir un unique bullet/paragraphe compact de 20+ technologies.
- Les compétences doivent être regroupées par familles lisibles quand le volume est élevé: Frontend, Backend, Cloud, DevOps, Data, Sécurité, Méthodes/Outils, Autres selon les termes source.
- Page 1: le bloc compétences ne doit pas pousser une expérience d'ouverture dans un espace ridicule. Si les compétences dépassent une densité raisonnable, elles doivent continuer sur `Compétences techniques (suite)` avant les expériences.
- Sur une page de suite compétences, utiliser une présentation scannable en deux colonnes ou par familles courtes; éviter un full-width inventaire de bullets isolés.
- Tous les items source importants doivent rester présents dans le texte extrait du PDF final, sauf doublons exacts et formulations équivalentes déjà présentes.

### Expériences / pagination

- Aucun titre/date/rôle d'expérience ne doit rester seul en bas de page.
- Une expérience peut continuer sur la page suivante, mais son ouverture doit être gardée avec au moins le premier heading et la première ligne/bullet utile.
- La première expérience doit passer par les mêmes règles de keep-together que les expériences suivantes.
- Si les compétences débordent, les expériences doivent démarrer proprement sur une nouvelle page avec marge haute sûre, pas dans le reste d'une page saturée.
- La dernière page ne doit pas être quasi vide si un compactage ou un déplacement raisonnable peut l'éviter.

### QA / blocage

- La QA doit échouer sur des défauts objectivables de layout, pas seulement sur overflow/contact.
- Le rapport QA doit expliquer le défaut avec page, type, coordonnées/extrait quand applicable.
- Les tests doivent inclure un cas synthétique Oussama-like: compétences longues + première expérience + saut de page fragile.
- Le worker ne doit pas marquer `ready` si la QA layout détecte un défaut bloquant.

---

## Plan d'implémentation TDD

### Task 1: Ajouter un test rouge pour le regroupement intelligent des compétences

**Objective:** Prouver que les longues listes de compétences ne doivent plus devenir un seul item `; ; ;` illisible.

**Files:**
- Modify test: `workers/cv-worker/tests/test_structuring_long_cv.py`
- Modify code later: `workers/cv-worker/src/structuring.py:308-318`

**Step 1: Write failing test**

Ajouter un test dans `LongCvStructuringTest`:

```python
def test_long_skills_are_split_into_readable_families_not_single_wall(self):
    data = {
        "name": "OUSSAMA",
        "title": "Développeur Full Stack",
        "formations": [],
        "skills": [{
            "category": "Compétences techniques",
            "items": [
                "React", "Next.js", "Vue.js", "TypeScript", "HTML", "CSS",
                "Node.js", "Java", "Spring", "PHP", "Symfony", "Python", "SQL Server",
                "AWS", "Docker", "Kubernetes", "Terraform", "GitLab CI", "Jenkins",
                "Power BI", "PostgreSQL", "MongoDB", "Redis", "Jira", "Confluence",
            ],
        }],
        "experiences": [],
    }

    synthesized = apply_client_synthesis_policy(data, mode="standard")
    categories = synthesized["skills"]

    assert len(categories) >= 4
    assert any(cat["category"] == "Frontend" for cat in categories)
    assert any(cat["category"] == "Backend" for cat in categories)
    assert any(cat["category"] == "Cloud / DevOps" for cat in categories)
    assert all(len(cat["items"]) <= 8 for cat in categories)
    assert not any(";" in item and len(item) > 120 for cat in categories for item in cat["items"])
```

**Step 2: Run RED**

Run:

```bash
PYTHONPATH=workers/cv-worker pytest -q workers/cv-worker/tests/test_structuring_long_cv.py::LongCvStructuringTest::test_long_skills_are_split_into_readable_families_not_single_wall
```

Expected: FAIL, because current `_group_long_skills` returns one category with one semicolon-joined item.

**Step 3: Implement minimal code**

Replace `_group_long_skills` behavior in `workers/cv-worker/src/structuring.py`:

- Deduplicate case-insensitively while preserving source wording.
- Classify individual terms into families using `_ENV_FAMILIES`.
- Merge Cloud and DevOps into display category `Cloud / DevOps` to avoid tiny fragmented blocks.
- Add a fallback `Méthodes / Outils` for terms matching `jira`, `confluence`, `agile`, `scrum`, `kanban`, `figma`, `postman`, `git` when not already Cloud/DevOps.
- Keep `Autres` only for remaining terms.
- Split any family longer than 8 items into chunks named `Category` then `Category (suite)`.
- For short categories (`<= max_items`), preserve current behavior.

Do not drop terms. Do not invent technologies.

**Step 4: Run GREEN**

Run the single test, then:

```bash
PYTHONPATH=workers/cv-worker pytest -q workers/cv-worker/tests/test_structuring_long_cv.py workers/cv-worker/tests/test_structuring.py
```

Expected: PASS.

---

### Task 2: Ajouter un test rouge pour l'équilibrage réel des colonnes de compétences page 1

**Objective:** Empêcher une répartition alternée qui crée une colonne visuellement surchargée.

**Files:**
- Modify test: `workers/cv-worker/tests/test_renderer_overflow.py`
- Modify code later: `/root/.hermes/scripts/whub_cv_renderer.py:287-329`

**Step 1: Write failing test**

Ajouter un test renderer qui importe le renderer par chemin ou rend un PDF synthétique avec catégories de hauteurs très différentes. Vérifier par extraction des positions PyMuPDF que les catégories longues ne sont pas toutes dans la même colonne.

Test conseillé:

```python
def test_skill_columns_are_balanced_by_measured_height_not_alternating_order(self):
    data = {
        'name': 'OUSSAMA',
        'title': 'Développeur Full Stack Senior',
        'formations': [],
        'skills': [
            {'category': 'Frontend', 'items': [f'React compétence longue {i}' for i in range(1, 16)]},
            {'category': 'Backend', 'items': ['Node.js', 'Java']},
            {'category': 'Cloud / DevOps', 'items': [f'AWS Kubernetes Terraform {i}' for i in range(1, 14)]},
            {'category': 'Data', 'items': ['SQL', 'PostgreSQL']},
            {'category': 'Méthodes / Outils', 'items': ['Agile', 'Jira', 'Confluence']},
        ],
        'experiences': [{
            'date': '2024',
            'role': 'DÉVELOPPEUR FULL STACK CHEZ CLIENT',
            'sections': [{'heading': 'Missions clés', 'content': ['Développement applicatif', 'Maintenance évolutive']}],
        }],
    }
    pdf_path = self.render(data)
    doc = fitz.open(str(pdf_path))
    page_text = doc[0].get_text('dict')
    category_blocks = []
    for block in page_text['blocks']:
        if block.get('type') != 0:
            continue
        text = ''.join(span['text'] for line in block['lines'] for span in line['spans']).strip()
        if text in {'Frontend', 'Backend', 'Cloud / DevOps', 'Data', 'Méthodes / Outils'}:
            category_blocks.append((text, block['bbox'][0]))
    xs = {text: x for text, x in category_blocks}
    assert xs['Frontend'] != xs['Cloud / DevOps']
```

Expected RED: FAIL si l'alternance place deux gros blocs dans la même colonne selon l'ordre retenu.

**Step 2: Implement minimal code**

Changer `split_skill_columns_for_page`:

- Ne plus faire `columns = [skills[::2], skills[1::2]]`.
- Mesurer `skill_block_height(cat, width)`.
- Greedy stable: trier uniquement par ordre source, mais placer chaque catégorie dans la colonne ayant la hauteur courante la plus basse, en tenant compte du header et des items.
- Si une catégorie ne tient dans aucune colonne, la splitter item par item dans la colonne la plus basse puis pousser le reste en overflow.
- Conserver l'ordre relatif autant que possible; ne pas créer un tri alphabétique ou par taille qui changerait le sens métier.

**Step 3: Run tests**

```bash
PYTHONPATH=workers/cv-worker pytest -q workers/cv-worker/tests/test_renderer_overflow.py::RendererOverflowTest::test_skill_columns_are_balanced_by_measured_height_not_alternating_order
PYTHONPATH=workers/cv-worker pytest -q workers/cv-worker/tests/test_renderer_overflow.py
```

Expected: PASS, no text below margin.

---

### Task 3: Rendre la suite des compétences scannable et testée

**Objective:** Les compétences overflow doivent rester lisibles, pas devenir une longue page full-width monotone.

**Files:**
- Modify test: `workers/cv-worker/tests/test_renderer_overflow.py`
- Modify code: `/root/.hermes/scripts/whub_cv_renderer.py:339-350`

**Step 1: Write failing test**

Adapter `test_long_page_one_skill_list_continues_before_experiences` ou ajouter un nouveau test:

- Générer 6 catégories longues.
- Vérifier que la page `Compétences techniques (suite)` contient les catégories dans deux zones x distinctes (`bbox[0]` gauche et droite), pas seulement une colonne full width.
- Vérifier que toutes les compétences sont présentes.
- Vérifier que l'expérience démarre après la suite compétences, avec `ARCHITECTE...` présent.

**Step 2: Implement minimal code**

Modifier `render_skill_overflow`:

- Utiliser deux colonnes full-page `left` et `left + 245` environ, largeur environ 220 chacune.
- Réutiliser la logique de mesure/placement par hauteur.
- Si une catégorie ou un item ne tient pas, passer colonne suivante puis page suivante avec heading `Compétences techniques (suite)`.
- Ne jamais dessiner un heading de catégorie sans au moins son premier item.

**Step 3: Run tests**

```bash
PYTHONPATH=workers/cv-worker pytest -q workers/cv-worker/tests/test_renderer_overflow.py
```

Expected: PASS.

---

### Task 4: Appliquer le keep-together à la première expérience

**Objective:** Corriger le saut de page Oussama où l'expérience démarre mal parce que la première expérience est rendue en chemin spécial.

**Files:**
- Modify test: `workers/cv-worker/tests/test_renderer_overflow.py`
- Modify code: `/root/.hermes/scripts/whub_cv_renderer.py:406-414`

**Step 1: Write failing test**

Créer un CV synthétique avec des compétences qui laissent juste assez de place pour afficher la date/rôle mais pas le premier bullet. Assertion: la première expérience doit être déplacée sur page suivante si son ouverture complète ne tient pas.

Test par extraction PyMuPDF:

- Trouver le bloc `2024` et `DÉVELOPPEUR FULL STACK CHEZ CLIENT`.
- Trouver le premier bullet `Développement d'une plateforme...`.
- Assert qu'ils sont sur la même page quand la section ouvre l'expérience.
- Assert pas de page où le rôle est le dernier bloc utile sous `y > page_height - 90`.

**Step 2: Implement minimal code**

Dans `render`, remplacer le rendu manuel de `first` par:

```python
first, rest = exps[0], exps[1:]
self.render_experience(first)
```

Puis ajuster l'espacement si nécessaire pour ne pas doubler le `self.y += 13`.

Attention: vérifier que cela ne force pas toujours la première expérience sur page 2. Si elle tient proprement sur page 1, elle doit y rester.

**Step 3: Run tests**

```bash
PYTHONPATH=workers/cv-worker pytest -q workers/cv-worker/tests/test_renderer_overflow.py
```

Expected: PASS.

---

### Task 5: Ajouter une QA layout objectivable

**Objective:** Bloquer les PDF qui passent techniquement mais échouent visuellement sur des règles simples.

**Files:**
- Modify test: `workers/cv-worker/tests/test_qa_text_overflow.py` or create `workers/cv-worker/tests/test_qa_layout_quality.py`
- Modify code: `workers/cv-worker/src/qa.py`

**Step 1: Write failing tests**

Ajouter des helpers PyMuPDF générant des PDF synthétiques et tester trois défauts:

1. `test_layout_quality_reports_orphan_experience_heading_near_bottom`
   - Page avec texte `2024`, `DÉVELOPPEUR FULL STACK CHEZ CLIENT` à y=790 et aucun contenu utile après.
   - Expected QAError avec `layout_quality_hits[0]['type'] == 'orphan_experience_opening'`.

2. `test_layout_quality_reports_nearly_empty_last_page`
   - PDF de 2 pages, dernière page avec seulement un nom/header ou moins de 3 blocs utiles.
   - Expected QAError type `sparse_last_page`.
   - Prévoir une exemption si le document n'a qu'une page.

3. `test_layout_quality_allows_normal_multi_page_cv`
   - PDF de 2 pages avec plusieurs blocs utiles sur la dernière page.
   - Expected no layout hit.

**Step 2: Implement minimal code**

Dans `qa.py`:

- Ajouter `find_layout_quality_issues(doc)`.
- Extraire blocs texte utiles en ignorant le nom violet de continuation si possible et titres purement décoratifs.
- Heuristique orphan opening:
  - Détecter ligne date/rôle avec regex dates années/mois ou rôles uppercase contenant `CHEZ`, `CLIENT`, `CONSULTANT`, `DÉVELOPPEUR`, `ARCHITECTE`, etc.
  - Si bbox bottom > page_height - 110 et aucun bloc utile après sur la même page, signaler.
- Heuristique sparse last page:
  - Si `doc.page_count > 1`, compter blocs utiles hors header nom/logo; si < 3 ou hauteur totale texte utile < 120 pt, signaler.
  - Ne pas bloquer les pages `Compétences techniques (suite)` si elles contiennent plusieurs catégories/items.
- Ajouter `layout_quality_hits` au rapport `run_qa` et dans `passed`.

Le rapport doit rester sans secret/PII brute: extrait court 120-160 caractères max.

**Step 3: Run tests**

```bash
PYTHONPATH=workers/cv-worker pytest -q workers/cv-worker/tests/test_qa.py workers/cv-worker/tests/test_qa_text_overflow.py workers/cv-worker/tests/test_qa_layout_quality.py
```

Expected: PASS.

---

### Task 6: Créer un scénario renderer Oussama-like complet

**Objective:** Avoir une preuve anti-régression qui combine compétences longues, page de suite, première expérience et QA.

**Files:**
- Modify test: `workers/cv-worker/tests/test_renderer_overflow.py`
- Possibly modify code from earlier tasks only if this test exposes a gap.

**Step 1: Write failing/integration test**

Ajouter `test_oussama_like_cv_is_readable_and_keeps_all_facts`:

- `name`: `OUSSAMA`
- `title`: `Développeur Full Stack Senior`
- `formations`: 2 entrées.
- `skills`: 7 catégories, dont 2 très longues.
- `experiences`: 4 expériences dont la première récente avec 8 bullets, environnement technique long, les anciennes plus courtes.

Assertions:

- PDF existe et page_count >= 2.
- Tous les marqueurs de compétences clés existent dans le texte final: React, Next.js, Node.js, Java, Symfony, AWS, Docker, Kubernetes, SQL Server, Power BI, Jira.
- `Compétences techniques (suite)` existe seulement si nécessaire, mais si elle existe elle précède l'ouverture des expériences dans l'ordre du texte.
- `DÉVELOPPEUR FULL STACK` et son premier bullet sont sur la même page.
- `assert_no_text_below_margin(pdf_path)` passe.
- `run_qa(pdf_path)` passe si les fake assets sont reconnus par le vrai renderer.

**Step 2: Run test**

```bash
PYTHONPATH=workers/cv-worker pytest -q workers/cv-worker/tests/test_renderer_overflow.py::RendererOverflowTest::test_oussama_like_cv_is_readable_and_keeps_all_facts
```

Expected initially: likely FAIL before Tasks 1-5, PASS after.

---

### Task 7: Final gates sans déploiement

**Objective:** Vérifier localement sans restart worker/prod deploy.

Run:

```bash
python ~/.hermes/skills/user-workflows/whub-client-cv-generator/scripts/verify_whub_assets.py
python -m py_compile workers/cv-worker/src/structuring.py workers/cv-worker/src/qa.py workers/cv-worker/src/rendering.py /root/.hermes/scripts/whub_cv_renderer.py
PYTHONPATH=workers/cv-worker pytest -q workers/cv-worker/tests/test_structuring.py workers/cv-worker/tests/test_structuring_long_cv.py workers/cv-worker/tests/test_rendering.py workers/cv-worker/tests/test_renderer_overflow.py workers/cv-worker/tests/test_qa.py workers/cv-worker/tests/test_qa_text_overflow.py workers/cv-worker/tests/test_qa_layout_quality.py
npm test
```

Do not run `npm run build` unless the implementing task touches web code; build can create metadata files and the current layout work should stay worker/renderer-only.

Expected: all pass. No deployment. No worker restart. Block with `review-required` after code implementation.

---

## Reviewer checklist after implementation

- Inspect `git diff` and confirm no unrelated web changes were touched or reverted.
- Confirm renderer global script `/root/.hermes/scripts/whub_cv_renderer.py` was intentionally changed and py_compile passes.
- Confirm no candidate-contact guard was weakened.
- Confirm long skills are grouped by family without dropping exact terms.
- Confirm the first experience uses the same keep-together path as the rest.
- Confirm QA reports layout defects with structured `layout_quality_hits`.
- Render the Oussama-like synthetic fixture and inspect page 1 + last page visually if possible.
- Do not deploy or restart worker until final review explicitly says GO.
