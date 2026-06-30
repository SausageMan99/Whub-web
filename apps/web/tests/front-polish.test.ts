import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

test('final front polish — exposes premium motion tokens and micro-interaction classes', () => {
  const css = readFileSync(join(process.cwd(), 'app/globals.css'), 'utf8');

  assert.match(css, /@keyframes whub-fade-up/);
  assert.match(css, /@keyframes whub-soft-pulse/);
  assert.match(css, /\.reveal-up/);
  assert.match(css, /\.premium-card/);
  assert.match(css, /\.transfer-dropzone/);
  assert.match(css, /\.paper-texture/);
  assert.match(css, /mix-blend-mode: multiply/);
  assert.match(css, /@media \(prefers-reduced-motion: reduce\)/);
});

test('final front polish — main portal pages use premium motion affordances without adding CRM fields', () => {
  const newPage = readFileSync(join(process.cwd(), 'app/requests/new/page.tsx'), 'utf8');
  const newForm = readFileSync(join(process.cwd(), 'app/requests/new/NewRequestForm.tsx'), 'utf8');
  const dashboard = readFileSync(join(process.cwd(), 'app/dashboard/page.tsx'), 'utf8');
  const detail = readFileSync(join(process.cwd(), 'app/requests/[id]/page.tsx'), 'utf8');

  for (const source of [newPage, newForm, dashboard, detail]) {
    assert.match(source, /reveal-up|premium-card|transfer-dropzone|status-dot|motion-safe/);
  }

  assert.doesNotMatch(newForm, /name="title"/);
  assert.doesNotMatch(newForm, /name="priority"/);
  assert.doesNotMatch(newForm, /cv_intentions|formations|experiences|skills/);
});
