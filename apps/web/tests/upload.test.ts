import test, { before } from 'node:test';
import assert from 'node:assert/strict';
import { readFileSync } from 'node:fs';
import { join } from 'node:path';

let state = {
  user: { id: 'u1', email: 'test@whub.fr' } as { id: string; email: string } | null,
  allowed: { email: 'test@whub.fr', role: 'member' } as { email: string; role: string } | null,
  whitelistError: null as Error | null,
  uploadError: null as Error | null,
  signedUrl: 'https://signed-upload.local' as string | null,
  profileError: null as Error | null,
  profileThrow: null as Error | null,
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
            if (state.profileThrow) throw state.profileThrow;
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

let createRequest: (formData: FormData) => Promise<{ ok: boolean; requestId?: string; error?: string }>;
let prepareUpload: (input: { file: File; fileName: string; fileType: string }) => Promise<{ requestId: string; sourcePath: string; signedUrl: string }>;

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
  t.mock.module('@/lib/queue', {
    namedExports: {
      cvJobProducer: {
        enqueue: (payload: unknown) => {
          recordedCalls.push({ table: 'queue', method: 'enqueue', payload });
          return Promise.resolve();
        },
      },
      CVJobData: undefined,
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
  state.profileThrow = null;
  state.insertError = null;
  recordedCalls = [];
}

function makePdfFile(name = 'cv.pdf') {
  return new File(['%PDF-1.7\nbody'], name, { type: 'application/pdf' });
}

function preparePdfUpload(name = 'cv.pdf') {
  const file = makePdfFile(name);
  return prepareUpload({ file, fileName: file.name, fileType: file.type });
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

async function captureConsoleError<T>(run: () => Promise<T>): Promise<{ result: T; logs: unknown[][] }> {
  const original = console.error;
  const logs: unknown[][] = [];
  console.error = (...args: unknown[]) => {
    logs.push(args);
  };
  try {
    return { result: await run(), logs };
  } finally {
    console.error = original;
  }
}

function assertCreateRequestFailureLog(
  logs: unknown[][],
  stage: string,
  requestId: string | null,
  message?: string,
) {
  assert.equal(logs.length, 1);
  assert.equal(logs[0][0], 'createRequest failed');
  const payload = logs[0][1] as { stage?: string; requestId?: string | null; message?: string; source_path?: string };
  assert.equal(payload.stage, stage);
  assert.equal(payload.requestId, requestId);
  assert.equal(payload.source_path, undefined);
  if (message) assert.equal(payload.message, message);
}

test('prepareUpload — creates signed upload URL even in auth-disabled mode', async () => {
  reset(false);
  const result = await preparePdfUpload();
  assert.equal(result.signedUrl, 'https://signed-upload.local');
  assert.match(result.requestId, /^[0-9a-f-]{36}$/);
});

test('prepareUpload — creates signed upload URL with sanitized source path', async () => {
  reset();
  const result = await preparePdfUpload('my cv.pdf');

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
  await assert.rejects(() => preparePdfUpload(), /REDIRECT \/requests\/new\?error=upload_failed/);
});

test('createRequest — creates a request even in auth-disabled mode', async () => {
  reset(false);
  assert.deepEqual(await createRequest(makePreparedForm()), {
    ok: true,
    requestId: '11111111-1111-4111-8111-111111111111',
  });
});

test('createRequest — ignores legacy whitelist state in auth-disabled mode', async () => {
  reset();
  state.allowed = null;
  assert.deepEqual(await createRequest(makePreparedForm()), {
    ok: true,
    requestId: '11111111-1111-4111-8111-111111111111',
  });
});

test('createRequest — requires prepared upload metadata and logs missing_upload_metadata', async () => {
  reset();
  const { result, logs } = await captureConsoleError(() => createRequest(new FormData()));
  assert.deepEqual(result, { ok: false, error: 'request_failed' });
  assertCreateRequestFailureLog(logs, 'missing_upload_metadata', null, 'unknown');
});

test('createRequest — inserts correct row into cv_requests and returns success instead of throwing redirect', async () => {
  reset();
  assert.deepEqual(await createRequest(makePreparedForm()), {
    ok: true,
    requestId: '11111111-1111-4111-8111-111111111111',
  });

  const insertCall = recordedCalls.find((c) => c.table === 'cv_requests' && c.method === 'insert');
  assert.ok(insertCall, 'insert call should exist');
  const row = insertCall!.payload as Record<string, unknown>;

  assert.equal(row.id, '11111111-1111-4111-8111-111111111111');
  // Telegram-like contract: title is server-fixed, never user-controlled.
  assert.equal(row.title, 'CV source');
  assert.equal(row.candidate_first_name, 'Alice');
  assert.equal(row.origin, 'web_portal');
  assert.equal(row.workflow, 'telegram_whub_cv_generation');
  assert.equal(row.instructions, 'Do it well');
  assert.equal(row.priority, 'high');
  assert.equal(row.status, 'submitted');
  assert.equal(row.source_file_path, '11111111-1111-4111-8111-111111111111/source/cv.pdf');
  assert.equal(row.source_file_name, 'cv.pdf');
  assert.equal(row.source_file_mime, 'application/pdf');
  assert.equal(row.source_file_size, 8);
  // Telegram-like contract: portal must never store structured CRM fields.
  assert.equal(row.skills, undefined);
  assert.equal(row.experiences, undefined);
  assert.equal(row.formations, undefined);
  assert.equal(row.candidate_title, undefined);
});

test('createRequest — enqueues job data with candidate first name', async () => {
  reset();
  assert.deepEqual(await createRequest(makePreparedForm()), {
    ok: true,
    requestId: '11111111-1111-4111-8111-111111111111',
  });

  const queueCall = recordedCalls.find((c) => c.table === 'queue' && c.method === 'enqueue');
  assert.ok(queueCall, 'queue enqueue call should exist');
  const payload = queueCall!.payload as Record<string, unknown>;
  assert.equal(payload.requestId, '11111111-1111-4111-8111-111111111111');
  assert.equal(payload.candidateFirstName, 'Alice');
  assert.equal(payload.instructions, 'Do it well');
});

test('createRequest — returns request_failed and logs cv_requests_insert on insert error', async () => {
  reset();
  state.insertError = new Error('boom');
  const { result, logs } = await captureConsoleError(() => createRequest(makePreparedForm()));
  assert.deepEqual(result, { ok: false, error: 'request_failed' });
  assertCreateRequestFailureLog(logs, 'cv_requests_insert', '11111111-1111-4111-8111-111111111111', 'boom');
});

test('createRequest — trims candidate first name before insert', async () => {
  reset();
  assert.deepEqual(await createRequest(makePreparedForm({ candidate_first_name: '  Jérémy  ' })), {
    ok: true,
    requestId: '11111111-1111-4111-8111-111111111111',
  });

  const insertCall = recordedCalls.find((c) => c.table === 'cv_requests' && c.method === 'insert');
  assert.ok(insertCall, 'insert call should exist');
  const row = insertCall!.payload as Record<string, unknown>;
  assert.equal(row.candidate_first_name, 'Jérémy');
});

test('new request page — exposes upload, first-name and message workflow without advanced fields', () => {
  const source = readFileSync(join(process.cwd(), 'app/requests/new/page.tsx'), 'utf8');
  const formSource = readFileSync(join(process.cwd(), 'app/requests/new/NewRequestForm.tsx'), 'utf8');

  assert.match(source, /Un seul flux: CV source \+ message libre\./);
  assert.match(source, /Même logique que Telegram Hermes/);
  assert.match(formSource, /name="file"/);
  assert.match(formSource, /name="candidate_first_name"/);
  assert.match(formSource, /Prénom du candidat/);
  assert.match(formSource, /name="instructions"/);
  assert.match(formSource, /Générer le CV/);
  assert.match(formSource, /Message \/ consigne complémentaire/);
  // Telegram-like contract: only file + candidate_first_name + instructions are user-controlled inputs.
  assert.doesNotMatch(formSource, /name="title"/);
  assert.doesNotMatch(formSource, /name="priority"/);
  assert.doesNotMatch(formSource, /name="skills"/);
  assert.doesNotMatch(formSource, /name="experiences"/);
  assert.doesNotMatch(formSource, /name="formations"/);
  assert.doesNotMatch(formSource, /name="candidate_title"/);
  assert.doesNotMatch(formSource, /cv_intentions/);
  assert.doesNotMatch(formSource, /buildGuidedInstructions/);
});

test('createRequest — rejects missing candidate first name before cv_requests insert', async () => {
  reset();
  const fd = new FormData();
  fd.set('request_id', '11111111-1111-4111-8111-111111111111');
  fd.set('source_path', '11111111-1111-4111-8111-111111111111/source/my-cv.pdf');
  fd.set('source_file_name', 'my-cv.pdf');
  fd.set('source_file_size', '8');
  fd.set('source_file_mime', 'application/pdf');
  fd.set('instructions', 'Garder le CV fidèle.');

  const { result, logs } = await captureConsoleError(() => createRequest(fd));
  assert.deepEqual(result, { ok: false, error: 'candidate_first_name_required' });
  assertCreateRequestFailureLog(logs, 'missing_candidate_first_name', '11111111-1111-4111-8111-111111111111', 'unknown');
  assert.equal(recordedCalls.find((c) => c.table === 'cv_requests' && c.method === 'insert'), undefined);
});

test('createRequest — accepts empty instructions and stores an empty string', async () => {
  reset();
  const form = makePreparedForm({ instructions: '   ' });

  assert.deepEqual(await createRequest(form), {
    ok: true,
    requestId: '11111111-1111-4111-8111-111111111111',
  });

  const insertCall = recordedCalls.find((c) => c.table === 'cv_requests' && c.method === 'insert');
  assert.ok(insertCall, 'insert call should exist');
  const row = insertCall!.payload as Record<string, unknown>;
  assert.equal(row.instructions, '');
});
