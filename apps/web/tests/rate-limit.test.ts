import test from 'node:test';
import assert from 'node:assert/strict';

function redirect(url: string): never {
  const err = new Error(`REDIRECT ${url}`) as Error & { digest?: string };
  err.digest = `NEXT_REDIRECT;replace;${url};307;`;
  throw err;
}

function makeFormData() {
  const fd = new FormData();
  fd.set('email', 'user@whub.fr');
  fd.set('access_code', 'valid-code');
  return fd;
}

test('login Server Action rate limits after 5 requests per minute per IP', async (t) => {
  t.mock.module('next/navigation', { namedExports: { redirect } });
  t.mock.module('next/headers', {
    namedExports: {
      headers: () =>
        Promise.resolve({
          get: (name: string) => (name.toLowerCase() === 'x-forwarded-for' ? '203.0.113.10, 10.0.0.1' : null),
        }),
    },
  });
  t.mock.module('@/lib/access-code', {
    namedExports: {
      normalizeEmail: (value: unknown) => String(value ?? '').trim().toLowerCase(),
      verifyAccessCode: () => Promise.resolve(true),
    },
  });
  t.mock.module('@/lib/supabase/admin', {
    namedExports: {
      createSupabaseAdminClient: () => ({
        from: () => ({
          select: () => ({
            eq: () => ({ maybeSingle: () => Promise.resolve({ data: { email: 'user@whub.fr' }, error: null }) }),
          }),
        }),
        auth: {
          admin: {
            listUsers: () => Promise.resolve({ data: { users: [] }, error: null }),
            createUser: () => Promise.resolve({ error: null }),
            updateUserById: () => Promise.resolve({ error: null }),
          },
        },
      }),
    },
  });
  t.mock.module('@/lib/supabase/server', {
    namedExports: {
      createSupabaseServerClient: () =>
        Promise.resolve({ auth: { signInWithPassword: () => Promise.resolve({ error: null }) } }),
    },
  });

  const { login } = await import('../app/login/actions');

  for (let i = 0; i < 5; i += 1) {
    await assert.rejects(() => login(makeFormData()), /REDIRECT \/dashboard/);
  }

  await assert.rejects(() => login(makeFormData()), /REDIRECT \/login\?error=rate_limited/);
});

test('prepareUpload Server Action rate limits after 10 requests per minute per IP', async (t) => {
  t.mock.module('next/navigation', { namedExports: { redirect } });
  t.mock.module('next/headers', {
    namedExports: {
      headers: () =>
        Promise.resolve({
          get: (name: string) => (name.toLowerCase() === 'x-real-ip' ? '198.51.100.22' : null),
        }),
      cookies: () => Promise.resolve({ getAll: () => [], set: () => {} }),
    },
  });
  t.mock.module('@/lib/supabase/server', {
    namedExports: {
      createSupabaseServerClient: () =>
        Promise.resolve({ auth: { getUser: () => Promise.resolve({ data: { user: { id: 'u1', email: 'user@whub.fr' } } }) } }),
    },
  });
  t.mock.module('@/lib/supabase/admin', {
    namedExports: {
      createSupabaseAdminClient: () => ({
        from: () => ({
          select: () => ({
            eq: () => ({ maybeSingle: () => Promise.resolve({ data: { email: 'user@whub.fr', role: 'member' }, error: null }) }),
          }),
        }),
        storage: {
          from: () => ({
            createSignedUploadUrl: () => Promise.resolve({ data: { signedUrl: 'https://signed-upload.local' }, error: null }),
          }),
        },
      }),
    },
  });

  const { prepareUpload } = await import('../app/requests/new/actions');

  for (let i = 0; i < 10; i += 1) {
    const result = await prepareUpload({ fileName: 'cv.pdf', fileType: 'application/pdf' });
    assert.equal(result.signedUrl, 'https://signed-upload.local');
  }

  await assert.rejects(
    () => prepareUpload({ fileName: 'cv.pdf', fileType: 'application/pdf' }),
    /REDIRECT \/requests\/new\?error=rate_limited/,
  );
});
