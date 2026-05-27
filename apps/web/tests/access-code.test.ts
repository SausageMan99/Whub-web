import test from 'node:test';
import assert from 'node:assert/strict';
import { expectedAccessCodeFromEmail, isValidAccessCodeForEmail } from '../lib/access-code';

test('expectedAccessCodeFromEmail uses the email local part as the W hub access code', () => {
  assert.equal(expectedAccessCodeFromEmail('cdubosq@whub.fr'), 'cdubosq');
  assert.equal(expectedAccessCodeFromEmail('ADAVID@whub.fr'), 'adavid');
  assert.equal(expectedAccessCodeFromEmail('  ebronzini@wrecruiter.com  '), 'ebronzini');
});

test('isValidAccessCodeForEmail accepts only the normalized first-initial-lastname code', () => {
  assert.equal(isValidAccessCodeForEmail('cdubosq@whub.fr', 'cdubosq'), true);
  assert.equal(isValidAccessCodeForEmail('adavid@whub.fr', 'ADAVID'), true);
  assert.equal(isValidAccessCodeForEmail('adavid@whub.fr', 'a david'), false);
  assert.equal(isValidAccessCodeForEmail('adavid@whub.fr', 'cdubosq'), false);
});
