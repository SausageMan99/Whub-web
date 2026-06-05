# Plan — W hub CV Factory : fidélité stricte + mise en page intelligente

## Objectif

Mettre en place dans W hub CV Factory les retours faits sur le CV Oussama : le portail doit produire un CV W hub beau, lisible et bien paginé, sans jamais transformer le contenu original du CV.

Le résultat attendu n’est pas un CV “amélioré” par reformulation. C’est un copier-coller fidèle du fond, nettoyé uniquement des coordonnées candidat et mis en page avec la charte W hub.

## Contexte actuel

Le cas Oussama a montré deux familles de problèmes.

D’abord, le système peut transformer le contenu : titre modifié, expériences reformulées, synthèses ajoutées, missions condensées. C’est inacceptable pour l’usage W hub, parce que le CV remis au client doit correspondre au CV original.

Ensuite, la pagination actuelle raisonne encore trop mécaniquement : elle évite parfois une coupure en isolant trop les expériences, ce qui crée des pages vides. Les retours manuels ont montré un meilleur comportement attendu : regrouper EDF + BNP Paribas quand ça tient, regrouper STALLERGENES GREER + Banque de France + EMGS Group quand ça tient, et démarrer SAFILAIT sur la page suivante.

L’apprentissage produit est donc : préserver strictement le contenu, mais optimiser intelligemment le placement des blocs pour éviter à la fois les coupures moches et les pages vides.

## Principes non négociables

Le pipeline doit respecter ces règles :

1. Aucune expérience, mission, livrable, environnement technique, date, entreprise, formation ou compétence ne doit être reformulé sans consigne explicite.
2. Les coordonnées candidat doivent être supprimées : téléphone, email, LinkedIn, URL, adresse personnelle.
3. Le nom de famille ne doit pas apparaître ; prénom seul.
4. La mise en page peut changer l’ordre visuel des blocs uniquement si l’ordre chronologique/professionnel reste cohérent.
5. Une expérience ne doit pas être coupée au milieu si elle peut tenir entière dans l’espace restant ou sur une nouvelle page.
6. Une expérience peut partager une page avec la précédente si elle tient proprement.
7. Une page trop vide est un défaut qualité, pas une solution acceptable.
8. Une page dense peut être acceptable si elle reste lisible et évite un gaspillage de page.
9. Les seuils QA ne doivent pas remplacer le jugement métier : ils doivent signaler, mais le packing doit décider intelligemment.

## Approche proposée

Mettre en place une évolution en trois couches :

1. **Fidelity gate stricte** : empêcher les reformulations et synthèses non demandées.
2. **Layout packing par blocs** : mesurer les expériences et chercher le meilleur placement page par page.
3. **QA finale orientée métier** : vérifier contacts, fidélité, coupures, densité acceptable et pages vides.

Le changement doit être testé avec un fixture Oussama-like reproduisant précisément les retours.

## Étape 1 — Ajouter des fixtures de régression Oussama-like

Créer un fixture source extrait du CV Oussama, anonymisé si nécessaire, mais conservant les sections structurantes : EDF, BNP Paribas, STALLERGENES GREER, Banque de France, EMGS Group, SAFILAIT, HUWAEI, projets académiques.

Fichiers probables :

- `workers/cv-worker/tests/fixtures/oussama_source.txt`
- `workers/cv-worker/tests/fixtures/oussama_structured_faithful.json`

Le JSON doit contenir uniquement du texte présent dans le source, hors suppression des coordonnées et nom complet.

Validation attendue :

- aucun item d’expérience du JSON ne manque dans le texte source normalisé ;
- les phrases sensibles restent inchangées, par exemple : `Conceptualiser, développer et mettre en œuvre les robots logiciels pour automatiser les processus métier clés.` ;
- aucune phrase de synthèse W hub n’est présente ;
- aucun titre inventé type `Chef de projet RPA/IA`.

## Étape 2 — Renforcer la fidélité source

Modifier la validation pour bloquer les reformulations qui gardent le même sens mais changent le texte.

Fichiers probables :

- `workers/cv-worker/src/structuring.py`
- `workers/cv-worker/tests/test_structuring.py`
- `workers/cv-worker/tests/test_structuring_long_cv.py`

Travail à faire :

- ajouter une fonction dédiée de comparaison stricte des contenus d’expérience ;
- vérifier chaque bullet d’expérience contre le texte source normalisé ;
- autoriser uniquement les différences de casse, espaces, accents, ponctuation mineure et retours ligne ;
- bloquer les synonymes/reformulations comme `mettre en œuvre des robots` si la source dit `mettre en œuvre les robots` ;
- bloquer les sections `Synthèse mission` et les phrases `Synthèse W hub` sauf consigne explicite de CV court/synthèse ;
- vérifier que le titre principal reste source-backed.

Tests à ajouter :

- `test_rejects_rewritten_experience_bullets_even_when_topic_matches_source`
- `test_rejects_synthesis_whub_without_explicit_short_instruction`
- `test_title_must_be_source_backed_or_candidate_field_backed`
- `test_oussama_fixture_has_zero_missing_experience_items`

## Étape 3 — Neutraliser la synthèse par défaut

Le mode par défaut doit être faithful/complete.

Fichier principal :

- `workers/cv-worker/src/structuring.py`

Règles :

- `WHUB_CV_SYNTHESIS_MODE` doit rester `complete` par défaut ;
- une consigne guidée `CV standard W hub` ne doit jamais activer condensation ou reformulation ;
- seule une consigne explicite `CV court`, `synthèse`, `résumer`, `condensé`, `version courte client` peut activer une condensation ;
- même en mode court, la sortie doit afficher clairement que des éléments sont condensés, et ce mode ne doit pas être le défaut du portail.

Fichier UI à vérifier :

- `apps/web/app/requests/new/intentions.ts`

Point important : revoir les intentions guidées pour éviter les mots qui déclenchent une synthèse non voulue. Par exemple, `CV standard W hub` doit dire : `conserver le contenu source, améliorer uniquement la mise en page W hub`.

## Étape 4 — Créer un moteur de layout packing

Ajouter une étape de packing avant le rendu PDF.

Objectif : choisir où démarrent les expériences, en remplissant les pages proprement sans couper les expériences au mauvais endroit.

Fichiers probables :

- `workers/cv-worker/src/rendering.py`
- `workers/cv-worker/src/layout_retry.py`
- éventuellement nouveau fichier : `workers/cv-worker/src/layout_packing.py`
- `workers/cv-worker/tests/test_rendering.py`
- `workers/cv-worker/tests/test_main_layout_retry.py`
- nouveau test : `workers/cv-worker/tests/test_layout_packing.py`

Logique attendue :

- mesurer la hauteur estimée de chaque expérience complète ;
- mesurer aussi la hauteur minimale acceptable : titre + date + première section ;
- tenter plusieurs placements : garder sur page courante, saut avant expérience, saut avant groupe suivant ;
- choisir le placement qui minimise :
  - expérience coupée dès le début ;
  - page quasi vide ;
  - page excessivement dense ;
  - saut de page inutile ;
- accepter une densité plus élevée si cela permet de garder ensemble deux expériences cohérentes et lisibles ;
- ne jamais modifier le texte pour résoudre un problème de placement.

Le moteur doit produire des options de layout non destructives, par exemple :

```json
{
  "force_page_break_before_experience_indexes": [2, 5],
  "allow_grouping": true,
  "density_profile": "balanced"
}
```

Ces options ne doivent jamais changer `experiences[*].sections[*].content`.

## Étape 5 — Ajouter des règles de regroupement métier

Pour les CV consultants longs, la pagination doit favoriser des groupes cohérents.

Règles à implémenter :

- expérience récente longue + expérience suivante : les garder ensemble si la seconde tient entièrement ;
- si une expérience ne tient pas entièrement dans le reste de page, la démarrer page suivante ;
- si une page contient une seule expérience courte et beaucoup d’espace vide, tenter d’ajouter l’expérience suivante ;
- si deux expériences moyennes tiennent ensemble sans coupure, les grouper ;
- si trois expériences tiennent ensemble et restent lisibles, les grouper aussi ;
- les expériences de stage/projets peuvent être groupées plus agressivement que les expériences récentes longues.

Cas de régression Oussama attendu :

- page 2 : EDF + BNP Paribas ;
- page 3 : STALLERGENES GREER + Banque de France + EMGS Group ;
- page 4 : SAFILAIT + HUWAEI + projets académiques.

Cette règle doit émerger du packing, pas d’un hardcode sur les noms d’entreprises.

## Étape 6 — Adapter la QA layout

La QA actuelle peut signaler `page_too_dense` même quand la page est acceptable visuellement et métier-wise. Il faut raffiner la classification.

Fichiers probables :

- `workers/cv-worker/src/qa.py`
- `workers/cv-worker/tests/test_qa_layout.py`

Changements proposés :

- ajouter un signal `page_too_sparse` ou renforcer `last_page_sparse` pour détecter les pages trop vides ;
- distinguer `page_dense_but_acceptable` de `page_too_dense` ;
- ne pas bloquer ou dégrader un PDF uniquement parce qu’une page a plus de 3000 caractères si :
  - pas d’overflow ;
  - pas de contact ;
  - pas de glyph cassé ;
  - pas de coupure d’expérience problématique ;
  - groupement métier cohérent ;
- ajouter un code spécifique `experience_split_mid_block` pour les coupures réellement problématiques ;
- ajouter un code `page_underfilled_with_next_experience_fit` pour le cas signalé par Clément.

## Étape 7 — Ajouter une boucle de rerender déterministe

Le worker doit faire une première passe de rendu, inspecter la QA layout, puis rerender avec options de packing si nécessaire.

Fichiers probables :

- `workers/cv-worker/src/main.py`
- `workers/cv-worker/src/layout_retry.py`
- `workers/cv-worker/src/rendering.py`

Flow attendu :

```text
structure fidèle
→ source fidelity gate
→ layout packing initial
→ render
→ QA contact/fidélité/overflow/layout
→ si page vide ou coupure expérience : recompute packing
→ rerender une fois
→ QA finale
→ completed | draft_ready | failed
```

Règles :

- maximum 1 ou 2 rerenders déterministes ;
- jamais de nouvelle structuration LLM pour corriger un problème de mise en page ;
- les options de layout doivent être validées par `assert_layout_retry_preserves_content` ;
- si la fidélité échoue, aucun PDF ne doit passer en `draft_ready`.

## Étape 8 — Mettre à jour l’interface utilisateur

Le portail doit refléter la promesse produit : dépôt CV → CV W hub fidèle et bien mis en page.

Fichiers probables :

- `apps/web/app/requests/new/intentions.ts`
- `apps/web/app/requests/new/NewRequestForm.tsx`
- `apps/web/components/CvProgressBar.tsx`
- `apps/web/components/StatusBadge.tsx`
- `apps/web/lib/cv-ui.ts`

Changements :

- remplacer les formulations ambiguës qui encouragent la synthèse ;
- afficher clairement que le mode standard conserve le contenu original ;
- réserver le mode court à une intention explicite ;
- si `draft_ready`, afficher les avertissements layout sans masquer la fidélité ;
- ne jamais proposer “corriger le contenu” comme action automatique sans confirmation.

## Étape 9 — Tests et validation

Commandes de validation ciblées :

```bash
cd /root/whub-cv-factory/workers/cv-worker
PYTHONPATH=. pytest tests/test_structuring.py -q
PYTHONPATH=. pytest tests/test_structuring_long_cv.py -q
PYTHONPATH=. pytest tests/test_layout_packing.py -q
PYTHONPATH=. pytest tests/test_rendering.py -q
PYTHONPATH=. pytest tests/test_qa_layout.py -q
PYTHONPATH=. pytest tests/test_main_layout_retry.py -q
```

Validation renderer :

```bash
python ~/.hermes/skills/user-workflows/whub-client-cv-generator/scripts/verify_whub_assets.py
python -m py_compile workers/cv-worker/src/structuring.py workers/cv-worker/src/rendering.py workers/cv-worker/src/qa.py workers/cv-worker/src/main.py
```

Validation web si l’UI change :

```bash
cd /root/whub-cv-factory/apps/web
npm test -- --run
npm run build
```

Validation manuelle attendue sur fixture Oussama :

- PDF généré sans contact candidat ;
- prénom seul ;
- EDF + BNP sur la même page ;
- STALLERGENES + Banque de France + EMGS sur la même page ;
- SAFILAIT démarre page suivante ;
- aucune expérience coupée de manière sale ;
- aucun contenu d’expérience reformulé ;
- 0 item d’expérience manquant contre le CV source.

## Risques et arbitrages

Le principal risque est de trop compacter la typographie pour forcer les groupements. Il faut éviter de rendre le PDF illisible. Le packing doit préférer une page de plus si la lisibilité devient mauvaise.

Deuxième risque : une validation trop stricte peut rejeter de vrais cas où l’extraction PDF modifie légèrement le texte. La normalisation doit donc tolérer les différences de retours ligne, espaces, ponctuation et accents, mais pas les synonymes ou réécritures.

Troisième risque : les consignes utilisateur peuvent demander explicitement une synthèse. Dans ce cas, il faut autoriser un mode court, mais il doit être explicite, traçable et différent du mode standard.

Quatrième risque : les seuils QA actuels peuvent classer une page dense en draft alors qu’elle est business-acceptable. Il faut enrichir la QA plutôt que simplement augmenter les seuils.

## Questions ouvertes

1. Faut-il que le mode `CV court client` existe encore dans l’interface, ou vaut-il mieux le retirer tant que la fidélité stricte n’est pas stabilisée ?
2. Quel niveau de densité est acceptable pour W hub : priorité à 4 pages denses mais lisibles, ou 5 pages plus aérées ?
3. Les projets académiques doivent-ils rester dans `Expériences professionnelles` ou être rendus dans une section séparée quand le CV source les distingue ?
4. Les sections `Langues` et `Autres` doivent-elles rester dans les compétences ou être déplacées dans une colonne/section dédiée si le template évolue ?

## Critères de succès

Le chantier est réussi si, sur le cas Oussama et les futurs CV similaires :

- le contenu source est conservé sans reformulation ;
- les coordonnées candidat sont supprimées ;
- le PDF respecte la charte W hub ;
- les expériences sont paginées comme un humain le ferait ;
- les pages ne paraissent ni vides ni mécaniquement tassées ;
- les tests empêchent une régression vers la synthèse automatique ou les sauts de page absurdes.
