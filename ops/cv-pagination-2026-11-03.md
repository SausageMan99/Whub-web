# Pagination — 2026-11-03

Suite de `ops/cv-fidelity-qa-and-skills-2026-11-03.md`. Zahia (dernière page de 3 lignes), amina (page à 33 %)
et noel (dernière page de 241 caractères) passaient en draft_ready à cause de la mise en page.

## Causes (renderer `renderer/whub_cv_renderer.py`)

1. **Coupure à 2 850 caractères sans regarder la suite.** Chaque page était remplie jusqu'au seuil anti-crowding,
   puis le petit reste partait seul sur la page suivante.
2. **Une page ne se limite pas qu'aux caractères.** Noel a des puces courtes : sa page 9 était pleine en hauteur
   (83 %) avec 2 330 caractères seulement, et la dernière expérience partait seule en page 10.
3. **La page 1 était sous-comptée.** Le renderer ne comptait que le texte des expériences, alors que la QA compte
   tout : description, compétences, colonne latérale. Zahia montait à 3 484 caractères en page 1.
4. **Deux définitions de « page trop vide ».** Le renderer : ≤ 42 % et ≤ 1 200 caractères. La QA : ≤ 46 % et
   ≤ 1 700. Le renderer créait lui-même des pages que la QA signalait (amina).
5. **Ouverture d'expérience orpheline.** Une coupure de densité pouvait tomber juste après la date et le poste
   (noel, variante regroupée). Une première section d'une seule ligne (« Systèmes : macOS… ») ne suffit pas
   non plus sous un titre en bas de page.

## Corrections

- **Le renderer compte tout le texte de la page**, comme la QA.
- **Équilibrage des pages de suite.** À l'ouverture d'une page, il estime ce qui reste en caractères *et* en
  hauteur. Le nombre de pages nécessaires est le plus grand des deux. Si la dernière page n'aurait qu'un reliquat,
  le reste est réparti également sur ces pages ; sinon rien ne change, donc on n'ajoute pas de page.
- **Reliquat** : un reste de moins de 450 caractères qui tient physiquement reste sur la page, sans franchir la
  ligne QA des 3 000 caractères. Une puce ne fait plus franchir cette ligne non plus.
- **Page 1** : si les compétences, la colonne latérale et l'ouverture de la première expérience dépassent la ligne
  QA, les expériences commencent en page 2.
- **« Page trop vide »** : la même définition que la QA, mesurée sur le texte des expériences.
- **Ouverture d'expérience** : jamais de coupure de densité entre date/poste et la première section. Si celle-ci
  fait moins de 120 caractères, l'ouverture inclut aussi la section suivante.

## Moteur de variantes (`src/layout`)

- **Variante regroupée** : un gros CV dont la mise en page de base passe (expériences forcées sur leur propre
  page) essaie aussi cette variante.
- **Choix entre variantes** : à score égal, la plus courte gagne. Noel : 10 pages au lieu de 12.

## QA (`src/qa.py`) — faux positifs qui envoyaient en draft

- **`skill_overflow_page_created`** : il fallait seulement « (suite) » et un mot comme « outils » ou « data »
  n'importe où sur la page. La règle demande maintenant un *titre* de compétences en « (suite) » après la page 1,
  ou le titre « Compétences techniques (suite) » du renderer. Les blocs « X (suite) » que le renderer répartit
  dans la page 1 (dense, yannick) et « Recette (suite) » (amina) ne déclenchent plus l'alerte.
- **`pdf_fact_absent_from_source`** : il signalait le prénom du portail, imprimé en tête de page (yannick, dont le
  PDF ne contient pas de nom). Il signalait aussi les catégories de la taxonomie fermée W hub que le prompt impose
  (« Stack principale »). Cette taxonomie est désormais une constante (`WHUB_SKILL_CATEGORY_TAXONOMY`), partagée par
  le prompt et la QA. Un libellé hors taxonomie reste signalé.

## Résultats

Mise en page seule, sur les mêmes données structurées (`bakeoff_v2`) :

| CV | Avant | Après |
|---|---|---|
| zahia | draft, 4 p. (dernière page 205 car.) | **passed**, 4 p. équilibrées |
| amina | draft, 6 p. (page à 33 %) | **passed**, 5 p. |
| noel | draft, 10 p. (dernière page 241 car.) | **passed**, 10 p. |
| dense | draft (faux débordement) | **passed** |
| yannick | draft (faux débordement) | draft : son prénom n'était pas autorisé (corrigé depuis) |

Banc prod (11 CV), le 03/11 à la fin de la journée : **11/11, 7 ready, aucune alerte de pagination** (le matin :
3 ready). Les drafts restants viennent des contrôles de fidélité et changent d'une génération du modèle à l'autre :

- oussama : entreprise écrite autrement que dans la source ;
- hodard : « Niveau » retiré ;
- benjamin : mission reformulée, une fois sur trois ;
- yannick : annexe de compétences sans titre.

Ce sont de vrais écarts, que la relecture humaine doit voir.

## Point ouvert

Benjamin a parfois une page 1 à ~3 050 caractères, **sans aucune expérience** : description, 35 compétences et
colonne latérale. La QA la classe `page_dense_but_acceptable`, et toute alerte de mise en page envoie en
draft_ready. Le renderer ne peut l'alléger qu'en créant une page « Compétences (suite) », que la QA pénalise
davantage. Il faut une décision de règle : `page_dense_but_acceptable` seule doit-elle bloquer ready ?
