import test from 'node:test';
import assert from 'node:assert/strict';
import { buildCvDownloadFilename, getCvProgress } from '../lib/cv-ui';

test('buildCvDownloadFilename uses the candidate name and version number safely', () => {
  assert.equal(buildCvDownloadFilename('Habib Beghdadi', 1), 'Habib-Beghdadi-W-hub-v1.pdf');
  assert.equal(buildCvDownloadFilename('Élodie / Test', 2), 'Elodie-Test-W-hub-v2.pdf');
  assert.equal(buildCvDownloadFilename('', 3), 'CV-W-hub-v3.pdf');
});

test('getCvProgress exposes readable progress percentages from request status and worker events', () => {
  assert.deepEqual(getCvProgress('submitted', []), {
    percent: 15,
    label: 'Demande reçue',
    helper: 'Le CV est dans la file de production.'
  });
  assert.deepEqual(getCvProgress('processing', ['worker_claimed']), {
    percent: 35,
    label: 'Traitement lancé',
    helper: 'Le worker W hub a pris la demande en charge.'
  });
  assert.deepEqual(getCvProgress('processing', ['worker_claimed', 'extraction_done']), {
    percent: 60,
    label: 'Extraction terminée',
    helper: 'Le contenu du CV source est structuré pour le rendu W hub.'
  });
  assert.deepEqual(getCvProgress('ready', ['ready']), {
    percent: 100,
    label: 'CV prêt',
    helper: 'Le PDF final a passé la QA et peut être téléchargé.'
  });
});
