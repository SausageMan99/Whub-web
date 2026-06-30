import test from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

test('dashboard UI — uses a production inbox instead of a heavy CRM table', () => {
  const source = readFileSync(join(process.cwd(), 'app/dashboard/page.tsx'), 'utf8');

  assert.match(source, /File de production CV|Demandes récentes/);
  assert.match(source, /source_file_name/);
  assert.match(source, /Nouveau CV/);
  assert.match(source, /StatusBadge/);
  assert.doesNotMatch(source, /<table/);
  assert.doesNotMatch(source, /Total demandes/);
});

test('request detail page — keeps PDF, tracking and correction as the primary zones', () => {
  const source = readFileSync(join(process.cwd(), 'app/requests/[id]/page.tsx'), 'utf8');

  assert.match(source, /Suivi de génération/);
  assert.match(source, /Version actuelle|Versions générées/);
  assert.match(source, /Télécharger le PDF|Télécharger le brouillon/);
  assert.match(source, /RevisionComposer/);
  assert.doesNotMatch(source, /Stockage privé Supabase · \{/);
});
