import test, { before } from 'node:test';
import assert from 'node:assert/strict';

/* ---------- mutable state shared with mocks ---------- */
let state = {
  user: { id: 'u1', email: 'test@whub.fr' } as { id: string; email: string } | null,
  allowed: { email: 'test@whub.fr' } as { email: string } | null,
  version: {
    id: 'v1',
    request_id: 'req1',
    version_number: 2,
    final_pdf_path: 'req1/final/v2.pdf',
  } as {
    id: string;
    request_id: string;
    version_number: number;
    final_pdf_path: string | null;
  } | null,
  request: {
    candidate_first_name: 'Alice',
    title: 'Senior Dev',
    source_file_name: 'source.pdf',
  } as {
    candidate_first_name: string | null;
    title: string | null;
    source_file_name: string | null;
  } | null,
  signedUrl: 'https://signed.url/final.pdf' as string | null,
  signedError: null as Error | null,
};

let recordedCalls: {
  bucket: string;
  method: string;
  payload?: unknown;
}[] = [];

function makeAdminClient() {
  return {
    from(table: string): any {
      if (table === 'allowed_users') {
        return {
          select() {
            return {
              eq() {
                return {
                  maybeSingle: () =>
                    Promise.resolve({ data: state.allowed, error: null }),
                };
              },
            };
          },
        };
      }
      if (table === 'cv_versions') {
        return {
          select() {
            return {
              eq(_field: string, _val: string) {
                return {
                  eq(_nextField: string, _nextVal: string) {
                    return {
                      maybeSingle: () =>
                        Promise.resolve({
                          data: state.version,
                          error: null,
                        }),
                    };
                  },
                };
              },
            };
          },
        };
      }
      if (table === 'cv_requests') {
        return {
          select() {
            return {
              eq() {
                return {
                  maybeSingle: () =>
                    Promise.resolve({ data: state.request, error: null }),
                };
              },
            };
          },
        };
      }
      return {};
    },
    storage: {
      from(bucket: string) {
        return {
          createSignedUrl(path: string, expiresIn: number, options?: Record<string, unknown>) {
            recordedCalls.push({ bucket, method: 'createSignedUrl', payload: { path, expiresIn, options } });
            return Promise.resolve({
              data: state.signedUrl ? { signedUrl: state.signedUrl } : null,
              error: state.signedError,
            });
          },
        };
      },
    },
  };
}

let GET: (
  req: Request,
  ctx: { params: Promise<{ id: string; versionId: string }> }
) => Promise<Response>;

before(async (t) => {
  t.mock.module('next/navigation', {
    namedExports: {
      redirect: (url: string) => {
        throw new Error(`REDIRECT ${url}`);
      },
    },
  });
  t.mock.module('next/headers', {
    namedExports: {
      cookies: () =>
        Promise.resolve({
          getAll: () => [] as any[],
          set: () => {},
        }),
    },
  });
  t.mock.module('@/lib/supabase/server', {
    namedExports: {
      createSupabaseServerClient: () =>
        Promise.resolve({
          auth: {
            getUser: () =>
              Promise.resolve({
                data: { user: state.user },
              }),
          },
        }),
    },
  });
  t.mock.module('@/lib/supabase/admin', {
    namedExports: {
      createSupabaseAdminClient: () => makeAdminClient(),
    },
  });

  const mod = await import('../app/requests/[id]/download/[versionId]/route');
  GET = mod.GET;
});

/* ---------- helpers ---------- */
function reset(authenticated = true) {
  state.user = authenticated ? { id: 'u1', email: 'test@whub.fr' } : null;
  state.allowed = { email: 'test@whub.fr' };
  state.version = {
    id: 'v1',
    request_id: 'req1',
    version_number: 2,
    final_pdf_path: 'req1/final/v2.pdf',
  };
  state.request = {
    candidate_first_name: 'Alice',
    title: 'Senior Dev',
    source_file_name: 'source.pdf',
  };
  state.signedUrl = 'https://signed.url/final.pdf';
  state.signedError = null;
  recordedCalls = [];
}

async function callHandler(id: string, versionId: string) {
  return GET(new Request(`http://localhost/${id}/download/${versionId}`), {
    params: Promise.resolve({ id, versionId }),
  });
}

/* ---------- tests ---------- */

test('download — rejects unauthenticated users', async () => {
  reset(false);
  await assert.rejects(
    () => callHandler('req1', 'v1'),
    /REDIRECT \/login/
  );
});

test('download — blocks non-whitelisted users', async () => {
  reset();
  state.allowed = null;
  await assert.rejects(
    () => callHandler('req1', 'v1'),
    /REDIRECT \/login\?error=not_allowed/
  );
});

test('download — returns 404 when version row not found', async () => {
  reset();
  state.version = null;
  const res = await callHandler('req1', 'v1');
  assert.equal(res.status, 404);
  assert.equal(await res.text(), 'PDF non disponible');
});

test('download — returns 404 when version has no final_pdf_path', async () => {
  reset();
  state.version = {
    id: 'v1',
    request_id: 'req1',
    version_number: 1,
    final_pdf_path: null,
  };
  const res = await callHandler('req1', 'v1');
  assert.equal(res.status, 404);
});

test('download — generates signed URL with correct expiry (60*5) and download name', async () => {
  reset();
  await assert.rejects(
    () => callHandler('req1', 'v1'),
    /REDIRECT https:\/\/signed\.url\/final\.pdf/
  );

  const call = recordedCalls.find((c) => c.method === 'createSignedUrl');
  assert.ok(call, 'createSignedUrl should have been called');
  const payload = call!.payload as { expiresIn: number; options: { download: string } };
  assert.equal(payload.expiresIn, 300);
  assert.ok(payload.options.download.startsWith('Alice'));
  assert.ok(payload.options.download.includes('-W-hub-v2.pdf'));
});

test('download — filename includes version number', async () => {
  reset();
  state.version = {
    id: 'v3',
    request_id: 'req1',
    version_number: 5,
    final_pdf_path: 'req1/final/v5.pdf',
  };
  await assert.rejects(
    () => callHandler('req1', 'v3'),
    /REDIRECT https:\/\/signed\.url\/final\.pdf/
  );

  const call = recordedCalls.find((c) => c.method === 'createSignedUrl');
  const payload = call!.payload as { options: { download: string } };
  assert.ok(payload.options.download.includes('v5'));
});

test('download — 500 when signed URL generation fails', async () => {
  reset();
  state.signedError = new Error('storage down');
  const res = await callHandler('req1', 'v1');
  assert.equal(res.status, 500);
  assert.ok((await res.text()).includes('Impossible'));
});

test('download — falls back to title then source_file_name for filename', async () => {
  reset();
  state.request = {
    candidate_first_name: null,
    title: 'Super Job',
    source_file_name: 'backup.pdf',
  };
  await assert.rejects(
    () => callHandler('req1', 'v1'),
    /REDIRECT https:\/\/signed\.url\/final\.pdf/
  );

  const call = recordedCalls.find((c) => c.method === 'createSignedUrl');
  const payload = call!.payload as { options: { download: string } };
  assert.ok(payload.options.download.startsWith('Super-Job'));
});

test('download — falls back to source_file_name when candidate_first_name and title are null', async () => {
  reset();
  state.request = {
    candidate_first_name: null,
    title: null,
    source_file_name: 'original.pdf',
  };
  await assert.rejects(
    () => callHandler('req1', 'v1'),
    /REDIRECT https:\/\/signed\.url\/final\.pdf/
  );

  const call = recordedCalls.find((c) => c.method === 'createSignedUrl');
  const payload = call!.payload as { options: { download: string } };
  assert.ok(payload.options.download.startsWith('original'));
});
