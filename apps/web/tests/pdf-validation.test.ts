import test, { before } from 'node:test';
import assert from 'node:assert/strict';

const TEN_MB = 10 * 1024 * 1024;

let state = {
  user: { id: 'u1', email: 'test@whub.fr' } as { id: string; email: string } | null,
  allowed: { email: 'test@whub.fr', role: 'member' } as { email: string; role: string } | null,
  uploadError: null as Error | null,
  signedUrl: 'https://signed-upload.local' as string | null,
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
                  maybeSingle: () => Promise.resolve({ data: state.allowed, error: null }),
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

let prepareUpload: (input: { fileName: string; fileType: string; fileSize: number }) => Promise<{ requestId: string; sourcePath: string; signedUrl: string }>;

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
      headers: () =>
        Promise.resolve({
          get: () => null,
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
  prepareUpload = mod.prepareUpload;
});

function reset() {
  state.user = { id: 'u1', email: 'test@whub.fr' };
  state.allowed = { email: 'test@whub.fr', role: 'member' };
  state.uploadError = null;
  state.signedUrl = 'https://signed-upload.local';
  recordedCalls = [];
}

function makeFile(bytes: Uint8Array, options: { name?: string; type?: string } = {}) {
  const body = bytes.buffer.slice(bytes.byteOffset, bytes.byteOffset + bytes.byteLength) as ArrayBuffer;
  return new File([body], options.name ?? 'cv.pdf', { type: options.type ?? 'application/pdf' });
}

async function callPrepareUpload(file: File) {
  return prepareUpload({ fileName: file.name, fileType: file.type, fileSize: file.size });
}

test('prepareUpload — accepts PDF metadata at or below 10MB without sending the file body to the Server Action', async () => {
  reset();
  const file = makeFile(new TextEncoder().encode('%PDF-1.7\nbody'));

  const result = await callPrepareUpload(file);

  assert.equal(result.signedUrl, 'https://signed-upload.local');
  assert.match(result.sourcePath, /^[0-9a-f-]{36}\/source\/cv\.pdf$/);
  assert.equal(recordedCalls.length, 1);
});

test('prepareUpload — rejects PDFs larger than 10MB', async () => {
  reset();
  const bytes = new Uint8Array(TEN_MB + 1);
  bytes.set(new TextEncoder().encode('%PDF-'), 0);
  const file = makeFile(bytes);

  await assert.rejects(() => callPrepareUpload(file), /REDIRECT \/requests\/new\?error=file_too_large/);
  assert.equal(recordedCalls.length, 0, 'oversized PDF must not get a signed upload URL');
});
