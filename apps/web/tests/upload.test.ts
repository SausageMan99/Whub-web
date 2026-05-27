import test, { before } from 'node:test';
import assert from 'node:assert/strict';

/* ---------- mutable state shared with mocks ---------- */
let state = {
  user: { id: 'u1', email: 'test@whub.fr' } as { id: string; email: string } | null,
  allowed: { email: 'test@whub.fr', role: 'member' } as { email: string; role: string } | null,
  uploadError: null as Error | null,
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
                  maybeSingle: () =>
                    Promise.resolve({ data: state.allowed, error: null }),
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
      from() {
        return {
          upload(path: string, _file: unknown, meta?: Record<string, unknown>) {
            recordedCalls.push({
              table: 'storage.cv-sources',
              method: 'upload',
              payload: { path, contentType: meta?.contentType },
            });
            return Promise.resolve({ error: state.uploadError });
          },
        };
      },
    },
  };
}

let createRequest: (formData: FormData) => Promise<void>;

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

  const mod = await import('../app/requests/new/actions');
  createRequest = mod.createRequest;
});

/* ---------- helpers ---------- */
function reset(user = true) {
  state.user = user ? { id: 'u1', email: 'test@whub.fr' } : null;
  state.allowed = { email: 'test@whub.fr', role: 'member' };
  state.uploadError = null;
  state.profileError = null;
  state.insertError = null;
  recordedCalls = [];
}

function makeFormData(file: File, extra: Record<string, string> = {}) {
  const fd = new FormData();
  fd.append('file', file);
  fd.append('title', extra.title ?? 'T');
  fd.append('candidate_first_name', extra.candidate_first_name ?? 'Alice');
  fd.append('instructions', extra.instructions ?? '');
  fd.append('priority', extra.priority ?? 'normal');
  return fd;
}

/* ---------- tests ---------- */

test('createRequest — rejects unauthenticated users', async () => {
  reset(false);
  await assert.rejects(
    () => createRequest(makeFormData(new File(['%PDF-1.4'], 'cv.pdf', { type: 'application/pdf' }))),
    /REDIRECT \/login/
  );
});

test('createRequest — blocks non-whitelisted users', async () => {
  reset();
  state.allowed = null;
  await assert.rejects(
    () => createRequest(makeFormData(new File(['%PDF-1.4'], 'cv.pdf', { type: 'application/pdf' }))),
    /REDIRECT \/login\?error=not_allowed/
  );
});

test('createRequest — requires a non-empty file', async () => {
  reset();
  await assert.rejects(
    () => createRequest(makeFormData(new File([], 'empty.pdf', { type: 'application/pdf' }))),
    /REDIRECT \/requests\/new\?error=file_required/
  );
});

test('createRequest — requires application/pdf MIME type', async () => {
  reset();
  await assert.rejects(
    () => createRequest(makeFormData(new File(['not a pdf'], 'cv.txt', { type: 'text/plain' }))),
    /REDIRECT \/requests\/new\?error=pdf_required/
  );
});

test('createRequest — requires PDF magic bytes (%PDF)', async () => {
  reset();
  await assert.rejects(
    () => createRequest(makeFormData(new File(['hello world not pdf'], 'cv.pdf', { type: 'application/pdf' }))),
    /REDIRECT \/requests\/new\?error=pdf_required/
  );
});

test('createRequest — uploads file to storage with correct source_path', async () => {
  reset();
  const fd = makeFormData(
    new File(['%PDF-1.4'], 'my cv.pdf', { type: 'application/pdf' }),
    { title: ' Senior Dev ', candidate_first_name: ' Alice ', instructions: ' Do it well ', priority: 'high' }
  );

  await assert.rejects(
    () => createRequest(fd),
    /REDIRECT \/requests\//
  );

  const uploadCall = recordedCalls.find((c) => c.method === 'upload');
  assert.ok(uploadCall, 'upload call should exist');
  const payload = uploadCall!.payload as { path: string; contentType: string };
  assert.match(payload.path, /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}\/source\/my_cv\.pdf$/);
  assert.equal(payload.contentType, 'application/pdf');
});

test('createRequest — inserts correct row into cv_requests', async () => {
  reset();
  const fd = makeFormData(
    new File(['%PDF-1.4'], 'cv.pdf', { type: 'application/pdf' }),
    { title: ' Senior Dev ', candidate_first_name: ' Alice ', instructions: ' Do it well ', priority: 'high' }
  );

  await assert.rejects(
    () => createRequest(fd),
    /REDIRECT \/requests\//
  );

  const insertCall = recordedCalls.find((c) => c.table === 'cv_requests' && c.method === 'insert');
  assert.ok(insertCall, 'insert call should exist');
  const row = insertCall!.payload as Record<string, unknown>;

  assert.equal(row.title, 'Senior Dev');
  assert.equal(row.candidate_first_name, 'Alice');
  assert.equal(row.instructions, 'Do it well');
  assert.equal(row.priority, 'high');
  assert.equal(row.status, 'submitted');
  assert.equal(row.source_file_name, 'cv.pdf');
  assert.equal(row.source_file_mime, 'application/pdf');
  assert.equal(row.source_file_size, 8);
  assert.equal(typeof row.id, 'string');
  assert.match(row.source_file_path as string, /source\/cv\.pdf$/);
});

test('createRequest — redirects to upload_failed on storage error', async () => {
  reset();
  state.uploadError = new Error('boom');
  await assert.rejects(
    () => createRequest(makeFormData(new File(['%PDF-1.4'], 'cv.pdf', { type: 'application/pdf' }))),
    /REDIRECT \/requests\/new\?error=upload_failed/
  );
});

test('createRequest — redirects to profile_failed on profile upsert error', async () => {
  reset();
  state.profileError = new Error('boom');
  await assert.rejects(
    () => createRequest(makeFormData(new File(['%PDF-1.4'], 'cv.pdf', { type: 'application/pdf' }))),
    /REDIRECT \/requests\/new\?error=profile_failed/
  );
});

test('createRequest — redirects to request_failed on insert error', async () => {
  reset();
  state.insertError = new Error('boom');
  await assert.rejects(
    () => createRequest(makeFormData(new File(['%PDF-1.4'], 'cv.pdf', { type: 'application/pdf' }))),
    /REDIRECT \/requests\/new\?error=request_failed/
  );
});

test('createRequest — redirects to the new request page on success', async () => {
  reset();
  const fd = makeFormData(new File(['%PDF-1.4'], 'cv.pdf', { type: 'application/pdf' }));

  let redirectUrl: string | null = null;
  try {
    await createRequest(fd);
  } catch (err: any) {
    const m = err.message.match(/REDIRECT (.*)/);
    if (m) redirectUrl = m[1];
  }

  assert.ok(redirectUrl, 'should have redirected');
  assert.match(redirectUrl!, /^\/requests\/[0-9a-f-]{36}$/);
});
