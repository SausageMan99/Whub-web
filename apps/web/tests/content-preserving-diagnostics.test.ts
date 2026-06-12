import test from 'node:test';
import assert from 'node:assert/strict';
import {
  extractContentPreservingDiagnostics,
  formatDiagnosticForUser,
  type CvEvent,
} from '../lib/content-preserving-diagnostics';

const SAMPLE_EVENT: CvEvent = {
  event_type: 'content_preserving_shadow_evaluated',
  metadata: {
    chosen_strategy: 'compact',
    chosen_density: 'normal',
    missing_required_blocks_count: 2,
    used_fallback: false,
    provider_name: 'openai',
    duration_ms: 1200,
    variant_score: 0.87,
  },
  created_at: '2026-06-12T10:00:00.000Z',
};

test('content-preserving diagnostics — extract from shadow evaluated event', () => {
  const d = extractContentPreservingDiagnostics([SAMPLE_EVENT]);
  assert.equal(d.present, true);
  assert.equal(d.variant, 'compact');
  assert.equal(d.density, 'normal');
  assert.equal(d.missingBlocksCount, 2);
  assert.equal(d.usedFallback, false);
  assert.equal(d.providerName, 'openai');
  assert.equal(d.durationMs, 1200);
  assert.equal(d.score, 0.87);
});

test('content-preserving diagnostics — extract from shadow failed event', () => {
  const d = extractContentPreservingDiagnostics([
    {
      event_type: 'content_preserving_shadow_failed',
      metadata: {
        chosen_strategy: 'compact',
        chosen_density: 'normal',
        used_fallback: true,
        fallback_category: 'invalid_response',
        provider_name: 'openai',
      },
      created_at: '2026-06-12T10:00:00.000Z',
    },
  ]);
  assert.equal(d.present, true);
  assert.equal(d.usedFallback, true);
  assert.equal(d.fallbackCategory, 'invalid_response');
});

test('content-preserving diagnostics — returns present=false when no content_preserving event', () => {
  const d = extractContentPreservingDiagnostics([
    { event_type: 'worker_claimed', metadata: null, created_at: '2026-06-12T09:00:00.000Z' },
    { event_type: 'extraction_done', metadata: null, created_at: '2026-06-12T09:00:01.000Z' },
  ]);
  assert.equal(d.present, false);
});

test('content-preserving diagnostics — picks the latest content_preserving event', () => {
  const older: CvEvent = {
    event_type: 'content_preserving_shadow_evaluated',
    metadata: {
      chosen_strategy: 'natural',
      chosen_density: 'comfortable',
      missing_required_blocks_count: 5,
      used_fallback: false,
    },
    created_at: '2026-06-12T08:00:00.000Z',
  };
  const newer: CvEvent = {
    event_type: 'content_preserving_shadow_evaluated',
    metadata: {
      chosen_strategy: 'sidebar_heavy',
      chosen_density: 'compact',
      missing_required_blocks_count: 0,
      used_fallback: false,
    },
    created_at: '2026-06-12T10:00:00.000Z',
  };
  const d = extractContentPreservingDiagnostics([older, newer]);
  assert.equal(d.variant, 'sidebar_heavy');
  assert.equal(d.missingBlocksCount, 0);
});

test('content-preserving diagnostics — format translates variant to French', () => {
  const lines = formatDiagnosticForUser({
    present: true,
    variant: 'compact',
    density: 'normal',
  });
  const joined = lines.join(' | ');
  assert.match(joined, /compacte/);
  assert.doesNotMatch(joined, /payload|stack|json|trace/i);
});

test('content-preserving diagnostics — format does not leak PII from metadata', () => {
  const lines = formatDiagnosticForUser({
    present: true,
    variant: 'natural',
    density: 'normal',
    providerName: 'openai',
  });
  const joined = lines.join(' | ');
  // providerName is exposed by design, but no email/phone/linkedin/url from raw metadata
  // The format function only consumes typed fields, so any PII accidentally passed would
  // still be filtered by the typed contract. Sanity check the known forbidden patterns.
  assert.doesNotMatch(joined, /@gmail\.com|@wanadoo\.fr|06\d{8}/i);
  assert.doesNotMatch(joined, /linkedin\.com\/in\/|https?:\/\//i);
});

test('content-preserving diagnostics — format hides missing blocks fingerprints', () => {
  const lines = formatDiagnosticForUser({
    present: true,
    variant: 'natural',
    density: 'normal',
    missingBlocksCount: 3,
  });
  const joined = lines.join(' | ');
  assert.match(joined, /Blocs manquants:?\s*3/);
  // Fingerprints are 12-char hex strings. They must not appear in user-facing strings.
  assert.doesNotMatch(joined, /[a-f0-9]{12}/i);
});

test('content-preserving diagnostics — missing required blocks count singular vs plural', () => {
  const oneLine = formatDiagnosticForUser({
    present: true,
    variant: 'natural',
    density: 'normal',
    missingBlocksCount: 1,
  });
  const joined = oneLine.join(' | ');
  assert.match(joined, /Bloc manquant:?\s*1/);
  assert.doesNotMatch(joined, /Blocs manquants/);
});
