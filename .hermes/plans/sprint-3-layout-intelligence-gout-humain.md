# W hub CV Factory — Sprint 3 Layout Intelligence & goût humain

## Intention produit

Sprint 3 ne doit pas seulement ajouter des seuils QA. L'objectif est que le worker se comporte comme une personne W hub qui sait mettre un CV en page : comprendre la densité, choisir une pagination propre, équilibrer compétences/expériences, éviter les pages moches, et sortir un PDF client-facing sans babysitting de Clément.

Le benchmark reste humain : si une alternante/chargée communication W hub aurait produit un CV plus lisible à la main, le sprint n'est pas terminé.

## Non-négociables

- Fidélité source stricte : pas de réécriture, résumé, suppression ou invention de contenu sans consigne explicite.
- Le layout intelligence agit sur placement, regroupement, pagination, densité, variantes et warnings, pas sur le sens.
- Contacts, nom complet, URLs personnelles, mauvais assets, overflow, glyphes cassés et source-fidelity restent des hard blockers.
- Les défauts purement visuels peuvent devenir `draft_ready` uniquement si le PDF est sûr et fidèle.
- Aucun push, restart worker ou déploiement Vercel sans carte d'accord explicite Clément.

## Définition de réussite Sprint 3

1. Le repo contient une spec claire du moteur de goût humain : métriques, scores, variantes, seuils et preuves attendues.
2. Le worker peut générer plusieurs variantes de layout ou au moins plusieurs jeux d'options déterministes, scorer leur rendu PDF, puis choisir la meilleure variante sûre.
3. Les compétences longues sont rendues lisibles : colonnes équilibrées, blocs chunkés proprement, pas de pavés, pas de technologies supprimées.
4. Les expériences sont paginées avec anti-orphan, anti-crowding, anti-sparse-tail et choix de regroupement naturel.
5. La QA produit des preuves actionnables : page metrics, codes layout, éventuellement montage/screenshots dans `artifacts/` non commit.
6. Les cas réels/régressions Oussama/Zahia/Habib ou fixtures équivalentes sont couverts par tests + smoke local.
7. La review finale inspecte le diff, les tests, les PDFs générés et les preuves visuelles, pas seulement un statut Kanban.

## Cascade Kanban prévue

- S3-0 : baseline/spec/read-only audit des capacités existantes et cas de régression.
- S3-1 : moteur de métriques + scoring de goût humain sur PDF rendu.
- S3-1R : CTO/QA review scoring.
- S3-2 : layout variant selector / bounded rerender loop.
- S3-2R : CTO/QA review variant loop.
- S3-3 : compétences lisibles non destructives.
- S3-3R : CTO/QA review compétences.
- S3-4 : pagination expériences anti-orphan/anti-dense/anti-sparse.
- S3-4R : CTO/QA review pagination expériences.
- S3-5 : evidence ledger + smoke réel local multi-CV sans prod.
- S3-5R : CTO/QA review smoke et artefacts.
- S3-R : review finale indépendante.
- S3-CTO : verdict CTO final release-readiness.
- S3-H : accord explicite Clément, bloqué.
- S3-D : release prod uniquement après S3-CTO + S3-H.

## Gates obligatoires

Depuis `/root/whub-cv-factory` :

```bash
scripts/verify_all.sh
```

Depuis `/root/whub-cv-factory/workers/cv-worker` selon le scope :

```bash
PYTHONPATH=. pytest -q
python -m py_compile src/*.py
python /root/.hermes/skills/user-workflows/whub-client-cv-generator/scripts/verify_whub_assets.py
```

Pour tout changement renderer/QA/layout : produire au moins un smoke PDF local et une preuve page-level avec PyMuPDF dans `artifacts/` ou `/tmp`, sans commit.
