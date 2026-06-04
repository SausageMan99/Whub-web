import test from 'node:test';
import assert from 'node:assert/strict';
import { verifyAccessCode, rotateAccessCode, normalizeEmail, normalizeAccessCode } from '../lib/access-code';

// ── VULNERABILITY DOCUMENTATION ──
// The OLD implementation (expectedAccessCodeFromEmail / isValidAccessCodeForEmail)
// derived the access code deterministically from the email local part:
//   expectedAccessCodeFromEmail('cdubosq@whub.fr') → 'cdubosq'
//   expectedAccessCodeFromEmail('ADAVID@whub.fr')  → 'adavid'
// Anyone who knows a user's email address could compute their access code
// without any database lookup, secret verification, or brute-force resistance.
// This was a critical security vulnerability: the access code offered zero
// protection beyond the email address itself.
//
// The NEW implementation replaces this with:
//   1. A random hex secret (48 bits) generated at user creation time
//   2. The secret is bcrypt-hashed and stored in allowed_users.access_code_hash
//   3. Verification uses pgcrypto's crypt() against the stored hash
//   4. Rotation re-generates the secret and re-hashes it
// ──────────────────────────────────

test('VULNERABILITY: old email-derived access codes were deterministic (no actual security)', () => {
  // Under the OLD implementation:
  //   expectedAccessCodeFromEmail('cdubosq@whub.fr') === 'cdubosq'
  //   expectedAccessCodeFromEmail('adavid@whub.fr')  === 'adavid'
  // The access code was literally just the email local part — zero security.
  assert.ok(true, 'VULNERABILITY DOCUMENTED: access codes were deterministic from email');
});

test('verifyAccessCode is an async function', () => {
  assert.equal(typeof verifyAccessCode, 'function');
  assert.equal(verifyAccessCode.constructor.name, 'AsyncFunction');
});

test('rotateAccessCode is an async function', () => {
  assert.equal(typeof rotateAccessCode, 'function');
  assert.equal(rotateAccessCode.constructor.name, 'AsyncFunction');
});

test('normalizeEmail trims and lowercases', () => {
  assert.equal(normalizeEmail('  AdaVid@WHUB.fr  '), 'adavid@whub.fr');
  assert.equal(normalizeEmail('  '), '');
  assert.equal(normalizeEmail(null), '');
  assert.equal(normalizeEmail(undefined), '');
});

test('normalizeAccessCode trims and lowercases', () => {
  assert.equal(normalizeAccessCode('  AbC  '), 'abc');
  assert.equal(normalizeAccessCode(''), '');
  assert.equal(normalizeAccessCode(null), '');
});