import test from 'node:test';
import assert from 'node:assert/strict';
import { buildCvDownloadFilename, getCvProgress, getCvStatusLabel } from '../lib/cv-ui';

/* ---------- buildCvDownloadFilename ---------- */

test('buildCvDownloadFilename — basic candidate name + version', () => {
  assert.equal(buildCvDownloadFilename('Habib Beghdadi', 1), 'Habib-Beghdadi-W-hub-v1.pdf');
});

test('buildCvDownloadFilename — strips diacritics and cleans special chars', () => {
  assert.equal(buildCvDownloadFilename('Élodie / Test', 2), 'Elodie-Test-W-hub-v2.pdf');
  assert.equal(buildCvDownloadFilename('Jean-Pierre', 3), 'Jean-Pierre-W-hub-v3.pdf');
});

test('buildCvDownloadFilename — falls back to "CV" when name is empty', () => {
  assert.equal(buildCvDownloadFilename('', 3), 'CV-W-hub-v3.pdf');
  assert.equal(buildCvDownloadFilename(null, 4), 'CV-W-hub-v4.pdf');
  assert.equal(buildCvDownloadFilename(undefined, 5), 'CV-W-hub-v5.pdf');
});

test('buildCvDownloadFilename — handles version 0', () => {
  assert.equal(buildCvDownloadFilename('Alice', 0), 'Alice-W-hub-v0.pdf');
});

test('buildCvDownloadFilename — strips CV/Cv/cv in name', () => {
  assert.equal(buildCvDownloadFilename('CV Alice', 1), 'Alice-W-hub-v1.pdf');
  assert.equal(buildCvDownloadFilename('cv Bob', 1), 'Bob-W-hub-v1.pdf');
});

/* ---------- getCvProgress ---------- */

test('getCvProgress — submitted', () => {
  assert.deepEqual(getCvProgress('submitted', []), {
    percent: 15,
    label: 'En attente',
    helper: 'Le CV source attend sa prise en charge.',
  });
});

test('getCvProgress — processing with worker_claimed', () => {
  assert.deepEqual(getCvProgress('processing', ['worker_claimed']), {
    percent: 35,
    label: 'Analyse du CV',
    helper: 'Le worker W hub analyse le CV source et prépare la structuration.',
  });
});

test('getCvProgress — worker_claimed event alone', () => {
  assert.deepEqual(getCvProgress('submitted', ['worker_claimed']), {
    percent: 35,
    label: 'Analyse du CV',
    helper: 'Le worker W hub analyse le CV source et prépare la structuration.',
  });
});

test('getCvProgress — extraction_done event', () => {
  assert.deepEqual(getCvProgress('processing', ['extraction_done']), {
    percent: 60,
    label: 'Mise au format W hub',
    helper: 'Le contenu du CV source est structuré et prêt pour le contrôle qualité.',
  });
});

test('getCvProgress — ready status', () => {
  assert.deepEqual(getCvProgress('ready', []), {
    percent: 100,
    label: 'Prêt à télécharger',
    helper: 'Le PDF final a passé la QA et peut être téléchargé.',
  });
});

test('getCvProgress — ready event overrides status', () => {
  assert.deepEqual(getCvProgress('submitted', ['ready']), {
    percent: 100,
    label: 'Prêt à télécharger',
    helper: 'Le PDF final a passé la QA et peut être téléchargé.',
  });
});

test('getCvProgress — draft_ready', () => {
  assert.deepEqual(getCvProgress('draft_ready', []), {
    percent: 100,
    label: 'Brouillon prêt',
    helper: 'Le PDF peut être téléchargé pour relecture, avec des points qualité à corriger avant envoi client.',
  });
});

test('getCvProgress — failed', () => {
  assert.deepEqual(getCvProgress('failed', []), {
    percent: 100,
    label: 'À corriger',
    helper: "La génération n'a pas pu aboutir. Corrige la source ou la consigne avant de relancer.",
  });
});

test('getCvProgress — qa_failed', () => {
  assert.deepEqual(getCvProgress('qa_failed', []), {
    percent: 85,
    label: 'Contrôle qualité',
    helper: 'Le PDF a été généré mais un blocage de qualité empêche encore la livraison.',
  });
});

test('getCvProgress — revision_requested', () => {
  assert.deepEqual(getCvProgress('revision_requested', []), {
    percent: 20,
    label: 'À corriger',
    helper: 'Une correction a été demandée pour lancer la prochaine version.',
  });
});

test('getCvProgress — cancelled', () => {
  assert.deepEqual(getCvProgress('cancelled', []), {
    percent: 0,
    label: 'Annulé',
    helper: 'Cette demande n\u2019est plus en production.',
  });
});

test('getCvProgress — archived', () => {
  assert.deepEqual(getCvProgress('archived', []), {
    percent: 0,
    label: 'Archivé',
    helper: 'Cette demande n\u2019est plus en production.',
  });
});

test('getCvStatusLabel — needs_human_review uses business wording', () => {
  assert.equal(getCvStatusLabel('needs_human_review', []), 'Validation humaine');
  // Even if events would have promoted it to a different status, the
  // needs_human_review status itself always wins on the label.
  assert.equal(
    getCvStatusLabel('needs_human_review', ['ready', 'extraction_done']),
    'Validation humaine',
  );
});

test('getCvProgress — needs_human_review exposes a clear helper', () => {
  const progress = getCvProgress('needs_human_review', []);
  assert.equal(progress.label, 'Validation humaine');
  assert.match(progress.helper, /humain|relire|vérifier/i);
  // The progress bar should not look "100% finished" because no PDF was
  // produced. Pick a mid-range value.
  assert.ok(progress.percent >= 0 && progress.percent < 100, 'must not be 100');
});
