import test from 'node:test';
import assert from 'node:assert/strict';
import {
  draftReadyTitle,
  hardFailureCopy,
  isHardFailureStatus,
  normalizeDraftWarnings,
} from '../lib/request-detail-ui';

test('request detail UI — draft_ready exposes exact brouillon title', () => {
  assert.equal(draftReadyTitle('draft_ready'), 'PDF généré en brouillon — points qualité détectés');
  assert.equal(draftReadyTitle('ready'), null);
});

test('request detail UI — formats draft layout warnings without internal noise', () => {
  const warnings = normalizeDraftWarnings({
    layout_issues: [
      {
        code: 'page_too_dense',
        page: 2,
        message: 'Page 2 anormalement dense: 3200 caractères, 44 blocs',
      },
      {
        code: 'skill_block_too_long',
        page: 1,
        snippet: 'Cloud / DevOps AWS Azure Docker Kubernetes Terraform Helm',
      },
    ],
  });

  assert.deepEqual(warnings, [
    'Page 2 · Page trop dense — Page 2 anormalement dense: 3200 caractères, 44 blocs',
    'Page 1 · Bloc de compétences trop long — Cloud / DevOps AWS Azure Docker Kubernetes Terraform Helm',
  ]);
});

test('request detail UI — returns empty warnings when qa_report is absent or malformed', () => {
  assert.deepEqual(normalizeDraftWarnings(null), []);
  assert.deepEqual(normalizeDraftWarnings({ layout_issues: 'not-an-array' }), []);
});

test('request detail UI — completed status has no draft or failure copy', () => {
  assert.equal(draftReadyTitle('ready'), null);
  assert.equal(hardFailureCopy('ready'), null);
  assert.equal(isHardFailureStatus('ready'), false);
});

test('request detail UI — failed statuses get safe blocking copy', () => {
  assert.equal(isHardFailureStatus('qa_failed'), true);
  assert.equal(isHardFailureStatus('failed'), true);
  assert.match(hardFailureCopy('qa_failed')?.title ?? '', /Erreur bloquante/);
  assert.match(hardFailureCopy('qa_failed')?.body ?? '', /détail technique interne/);
  assert.match(hardFailureCopy('failed')?.title ?? '', /Erreur de génération/);
});
