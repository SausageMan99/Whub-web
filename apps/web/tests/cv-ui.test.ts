import test from 'node:test';
import assert from 'node:assert/strict';
import { buildCvDownloadFilename, getCvProgress } from '../lib/cv-ui';

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
    label: 'Demande reçue',
    helper: 'Le CV est dans la file de production.',
  });
});

test('getCvProgress — processing with worker_claimed', () => {
  assert.deepEqual(getCvProgress('processing', ['worker_claimed']), {
    percent: 35,
    label: 'Traitement lancé',
    helper: 'Le worker W hub a pris la demande en charge.',
  });
});

test('getCvProgress — worker_claimed event alone', () => {
  assert.deepEqual(getCvProgress('submitted', ['worker_claimed']), {
    percent: 35,
    label: 'Traitement lancé',
    helper: 'Le worker W hub a pris la demande en charge.',
  });
});

test('getCvProgress — extraction_done event', () => {
  assert.deepEqual(getCvProgress('processing', ['extraction_done']), {
    percent: 60,
    label: 'Extraction terminée',
    helper: 'Le contenu du CV source est structuré pour le rendu W hub.',
  });
});

test('getCvProgress — ready status', () => {
  assert.deepEqual(getCvProgress('ready', []), {
    percent: 100,
    label: 'CV prêt',
    helper: 'Le PDF final a passé la QA et peut être téléchargé.',
  });
});

test('getCvProgress — ready event overrides status', () => {
  assert.deepEqual(getCvProgress('submitted', ['ready']), {
    percent: 100,
    label: 'CV prêt',
    helper: 'Le PDF final a passé la QA et peut être téléchargé.',
  });
});

test('getCvProgress — failed', () => {
  assert.deepEqual(getCvProgress('failed', []), {
    percent: 100,
    label: 'Erreur',
    helper: 'La génération a échoué. Ouvre la demande pour voir le détail.',
  });
});

test('getCvProgress — qa_failed', () => {
  assert.deepEqual(getCvProgress('qa_failed', []), {
    percent: 85,
    label: 'QA à reprendre',
    helper: 'Le PDF a été généré mais n\u2019a pas passé le contrôle qualité.',
  });
});

test('getCvProgress — revision_requested', () => {
  assert.deepEqual(getCvProgress('revision_requested', []), {
    percent: 20,
    label: 'Correction demandée',
    helper: 'La demande est revenue dans la file pour une nouvelle version.',
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
