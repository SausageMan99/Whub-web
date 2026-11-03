# QA fidélité et compétences — 2026-11-03

Deux problèmes laissés par le choix du modèle (`ops/model-bakeoff-2026-11-02.md`) :

- **fausses alertes de fidélité** : elles envoyaient des CV complets en draft_ready ;
- **compétences de zahia** : le découpage était cassé.

## 1. Contrôle de couverture des expériences (`structuring.py`)

Le contrôle relève chaque mission du CV source et vérifie qu'elle figure dans le CV généré. Il lisait comme des missions :

| Cas | Ce qui était lu comme une mission | Correction |
|---|---|---|
| oussama | la date seule sur sa ligne (« 07/2022 – 01/2024 »), puis « Software Engineer chez BNP Paribas » : le mot « chez » manquait | une plage de dates seule ouvre une nouvelle expérience ; la ligne suivante est son en-tête, sauf puce ou suite de phrase |
| oussama, hodard | le prénom répété en haut de page, puis le titre | le prénom seul (`data["name"]`) ouvre un en-tête de page, ignoré sans couper la mission en cours |
| hodard | la colonne latérale (« D E S C R I P T I O N », compétences, centres d'intérêt) entre deux pages de missions | un titre en lettres espacées ferme la section ; « Missions (suite) » la rouvre |
| rayan | « Autres — suite » collé à la langue précédente | les titres « — suite » / « (suite) » sont reconnus |
| yannick | les puces Wingdings (``, ``) et les sous-puces Word « o », seules sur leur ligne, collaient une expérience entière en un seul élément | ces lignes deviennent « • texte » dès l'extraction : le modèle reçoit aussi un texte propre |
| yannick | « Environnement fonctionnel : … » collé à la dernière mission | une ligne « Libellé : valeur » commence un nouvel élément |

Le contrôle reste strict : une mission vraiment supprimée est toujours signalée (`tests/test_experience_coverage_layouts.py`).

Alertes restantes, toutes justifiées :

- **hodard** : le modèle a écrit la langue « B2 TOEIC 690 » au lieu de « Niveau B2 — TOEIC 690 ». La source n'a pas de titre « Environnement technique », et le modèle en a créé un.
- **yannick** : une annexe de compétences sans titre suit la dernière expérience. Ses libellés (« Principes architecturaux », « OUTILS ») et « Architecture monolithique » sont rangés dans les catégories W hub.

## 2. Compétences lues d'après la mise en page (`visual_skills_extraction.py`)

Sept CV du banc partagent un modèle Canva : deux colonnes, titres en lettres espacées, une colonne « Formations » à droite.
L'extraction texte mélange ces colonnes : la formation de zahia se retrouvait collée à « Azure EntraID ».
L'extracteur visuel existant ne connaissait qu'une liste figée de titres (cas Omar) et échouait sur les 11 CV.

Il lit maintenant les styles du PDF :

- **la section** : le titre « Compétences » en grand ;
- **les colonnes** : chaque ligne est rattachée au titre de section de sa colonne, donc la colonne Formations reste à part ;
- **les catégories** : lignes en **gras** (un titre sur deux lignes est recollé) ;
- **les compétences** : les puces « • », avec les lignes de suite rattachées à leur puce.

Une puce reste entière telle que le candidat l'a écrite (« CRM (PEGA, Salesforce) : audit, migration des données, plan de décommissionnement »).
Elle n'est découpée que si c'est une vraie liste d'outils (« Python, Java, Next.js »).
Les catégories hors compétences (langues, loisirs, réseaux sociaux) sont écartées, et « X (suite) » est fusionnée avec « X ».

Ces compétences remplacent celles du modèle seulement en cas de confiance élevée. Dans le doute, on garde les compétences actuelles :

- section non fermée par un autre titre (elle pourrait continuer page suivante) ;
- lignes sans catégorie ;
- élément de plus de 120 caractères ;
- fragments de phrase.

Le chemin Omar/Ezzoubir n'a pas changé.

| CV | Résultat |
|---|---|
| zahia | les 4 catégories du CV source, 28 compétences entières, sans la formation ni le prénom |
| hodard | 7 catégories du source, « DevOps / CI/CD (suite) » fusionnée |
| amina | 4 catégories ; avant, la section Compétences contenait le texte de toutes ses missions (76 éléments) |
| oussama, rayan, dense | catégories et éléments du source |
| thorez, sanitize | rejetés par la confiance (élément de 200 caractères, puces cassées) : compétences inchangées |

Vérifié : les compétences « disparues » chez hodard et rayan (KendoUI, SonarQube, Supabase…) viennent du texte des missions, et elles y restent.

Le parseur de secours (`skills_intelligence.py`) ne coupe plus aux virgules entre parenthèses (« Méthodologies agiles (certifiée PSPO) »).

## Banc prod — 03/11 après corrections

| Cas | Statut | Layout/global/fidélité | Pages | Alertes restantes |
|---|---|---|---|---|
| oussama | **ready** | 100/100/100 | 2 | — |
| zahia | draft_ready | 64/64/100 | 4 | pagination : dernière page de 3 lignes |
| thorez | **ready** | 100/100/100 | 1 | — |
| dense | draft_ready | 88/88/100 | 2 | 40 compétences, page de débordement (cas de test voulu) |
| sanitize | **ready** | 100/100/100 | 1 | — |
| hodard | draft_ready | 88/82/82 | 2 | « Niveau » retiré par le modèle |
| rayan | **ready** | 100/100/100 | 2 | — |
| amina | draft_ready | 88/88/100 | 6 | pagination : page trop vide |
| benjamin | **ready** | 100/100/100 | 2 | — |
| noel | **ready** | 100/100/100 | 9 | — |
| yannick | draft_ready | 88/82/82 | 10 | annexe de compétences sans titre |

**11/11, 6 ready** (matin du 03/11 : 3 ready). Hors prod : couverture 0.80 → 0.82, copie exacte 0.985 → 0.999.

Zahia passe de ready à draft_ready. Son contenu est meilleur, mais la page 1 est plus remplie et sa dernière page ne garde que 3 lignes.
La variante de mise en page de secours ne fait pas mieux. Cette pagination relève du moteur de mise en page (`src/layout`), pas de ce chantier.
