import test, { before } from 'node:test';
import assert from 'node:assert/strict';

let state = {
  user: { id: 'u1', email: 'test@whub.fr' } as { id: string; email: string } | null,
  allowed: { email: 'test@whub.fr', role: 'member' } as { email: string; role: string } | null,
  whitelistError: null as Error | null,
  uploadError: null as Error | null,
  signedUrl: 'https://signed-upload.local' as string | null,
  profileError: null as Error | null,
  insertError: null as Error | null,
};

let recordedCalls: { table: string; method: string; payload?: unknown }[] = [];

function makeAdminClient() {
  return {
    from(table: string): any {
      if (table === 'allowed_users') {
        return {
          select() {
            return {
              eq() {
                return {
                  maybeSingle: () => Promise.resolve({ data: state.allowed, error: state.whitelistError }),
                };
              },
            };
          },
        };
      }
      if (table === 'profiles') {
        return {
          upsert(payload: unknown) {
            recordedCalls.push({ table, method: 'upsert', payload });
            return Promise.resolve({ error: state.profileError });
          },
        };
      }
      if (table === 'cv_requests') {
        return {
          insert(payload: unknown) {
            recordedCalls.push({ table, method: 'insert', payload });
            return Promise.resolve({ error: state.insertError });
          },
        };
      }
      return {};
    },
    storage: {
      from(bucket: string) {
        return {
          createSignedUploadUrl(path: string) {
            recordedCalls.push({ table: `storage.${bucket}`, method: 'createSignedUploadUrl', payload: { path } });
            return Promise.resolve({
              data: state.signedUrl ? { signedUrl: state.signedUrl } : null,
              error: state.uploadError,
            });
          },
        };
      },
    },
  };
}

let createRequest: (formData: FormData) => Promise<void>;
let prepareUpload: (input: { fileName: string; fileType: string }) => Promise<{ requestId: string; sourcePath: string; signedUrl: string }>;

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
            getUser: () => Promise.resolve({ data: { user: state.user } }),
          },
        }),
    },
  });
  t.mock.module('@/lib/supabase/admin', {
    namedExports: {
      createSupabaseAdminClient: () => makeAdminClient(),
    },
  });

  const mod = await import('../app/requests/new/actions');
  createRequest = mod.createRequest;
  prepareUpload = mod.prepareUpload;
});

function reset(user = true) {
  state.user = user ? { id: 'u1', email: 'test@whub.fr' } : null;
  state.allowed = { email: 'test@whub.fr', role: 'member' };
  state.whitelistError = null;
  state.uploadError = null;
  state.signedUrl = 'https://signed-upload.local';
  state.profileError = null;
  state.insertError = null;
  recordedCalls = [];
}

function makePreparedForm(extra: Record<string, string> = {}) {
  const fd = new FormData();
  fd.set('request_id', extra.request_id ?? '11111111-1111-4111-8111-111111111111');
  fd.set('source_path', extra.source_path ?? '11111111-1111-4111-8111-111111111111/source/cv.pdf');
  fd.set('source_file_name', extra.source_file_name ?? 'cv.pdf');
  fd.set('source_file_size', extra.source_file_size ?? '8');
  fd.set('source_file_mime', extra.source_file_mime ?? 'application/pdf');
  fd.set('title', extra.title ?? ' Senior Dev ');
  fd.set('candidate_first_name', extra.candidate_first_name ?? ' Alice ');
  fd.set('instructions', extra.instructions ?? ' Do it well ');
  fd.set('priority', extra.priority ?? 'high');
  return fd;
}

test('prepareUpload — rejects unauthenticated users', async () => {
  reset(false);
  await assert.rejects(() => prepareUpload({ fileName: 'cv.pdf', fileType: 'application/pdf' }), /REDIRECT \/login/);
});

test('prepareUpload — creates signed upload URL with sanitized source path', async () => {
  reset();
  const result = await prepareUpload({ fileName: 'my cv.pdf', fileType: 'application/pdf' });

  assert.equal(result.signedUrl, 'https://signed-upload.local');
  assert.match(result.requestId, /^[0-9a-f-]{36}$/);
  assert.match(result.sourcePath, /^[0-9a-f-]{36}\/source\/my_cv\.pdf$/);
  const call = recordedCalls.find((c) => c.method === 'createSignedUploadUrl');
  assert.ok(call, 'signed upload call should exist');
  assert.deepEqual(call!.payload, { path: result.sourcePath });
});

test('prepareUpload — redirects to upload_failed on signed URL error', async () => {
  reset();
  state.uploadError = new Error('boom');
  await assert.rejects(() => prepareUpload({ fileName: 'cv.pdf', fileType: 'application/pdf' }), /REDIRECT \/requests\/new\?error=upload_failed/);
});

test('createRequest — rejects unauthenticated users', async () => {
  reset(false);
  await assert.rejects(() => createRequest(makePreparedForm()), /REDIRECT \/login/);
});

test('createRequest — propagates non-whitelisted users as not_allowed', async () => {
  reset();
  state.allowed = null;
  await assert.rejects(() => createRequest(makePreparedForm()), /not_allowed/);
});

test('createRequest — requires prepared upload metadata', async () => {
  reset();
  await assert.rejects(() => createRequest(new FormData()), /REDIRECT \/requests\/new\?error=request_failed/);
});

test('createRequest — inserts correct row into cv_requests', async () => {
  reset();
  await assert.rejects(() => createRequest(makePreparedForm()), /REDIRECT \/requests\/11111111-1111-4111-8111-111111111111/);

  const insertCall = recordedCalls.find((c) => c.table === 'cv_requests' && c.method === 'insert');
  assert.ok(insertCall, 'insert call should exist');
  const row = insertCall!.payload as Record<string, unknown>;

  assert.equal(row.id, '11111111-1111-4111-8111-111111111111');
  assert.equal(row.created_by, 'u1');
  assert.equal(row.title, 'Senior Dev');
  assert.equal(row.candidate_first_name, 'Alice');
  assert.equal(row.instructions, 'Do it well');
  assert.equal(row.priority, 'high');
  assert.equal(row.status, 'submitted');
  assert.equal(row.source_file_path, '11111111-1111-4111-8111-111111111111/source/cv.pdf');
  assert.equal(row.source_file_name, 'cv.pdf');
  assert.equal(row.source_file_mime, 'application/pdf');
  assert.equal(row.source_file_size, 8);
});

test('createRequest — redirects to profile_failed on profile upsert error', async () => {
  reset();
  state.profileError = new Error('boom');
  await assert.rejects(() => createRequest(makePreparedForm()), /REDIRECT \/requests\/new\?error=profile_failed/);
});

test('createRequest — redirects to request_failed on insert error', async () => {
  reset();
  state.insertError = new Error('boom');
  await assert.rejects(() => createRequest(makePreparedForm()), /REDIRECT \/requests\/new\?error=request_failed/);
});
