import test, { before } from 'node:test';
import assert from 'node:assert/strict';

let state = {
  user: { id: 'u1', email: 'test@whub.fr' } as { id: string; email: string } | null,
  allowed: { email: 'test@whub.fr', role: 'member' } as { email: string; role: string } | null,
  request: {
    id: 'req1',
    created_by: 'u1',
    current_version_id: 'v1',
    status: 'ready',
  } as { id: string; created_by: string; current_version_id: string | null; status: string } | null,
  currentVersion: {
    id: 'v1',
    version_number: 1,
    qa_status: 'passed',
  } as { id: string; version_number: number; qa_status: string } | null,
  commentInsert: null as Record<string, unknown> | null,
  requestUpdate: null as Record<string, unknown> | null,
  eventInsert: null as Record<string, unknown> | null,
  revalidated: [] as string[],
};

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
      if (table === 'cv_requests') {
        return {
          select() {
            return {
              eq() {
                return {
                  maybeSingle: () => Promise.resolve({ data: state.request, error: null }),
                };
              },
            };
          },
          update(payload: Record<string, unknown>) {
            state.requestUpdate = payload;
            return {
              eq() {
                return Promise.resolve({ error: null });
              },
            };
          },
        };
      }
      if (table === 'cv_comments') {
        return {
          insert(payload: Record<string, unknown>) {
            state.commentInsert = payload;
            return Promise.resolve({ error: null });
          },
        };
      }
      if (table === 'cv_versions') {
        return {
          select() {
            return {
              eq() {
                return {
                  maybeSingle: () => Promise.resolve({ data: state.currentVersion, error: null }),
                };
              },
            };
          },
        };
      }
      if (table === 'cv_events') {
        return {
          insert(payload: Record<string, unknown>) {
            state.eventInsert = payload;
            return Promise.resolve({ error: null });
          },
        };
      }
      return {};
    },
  };
}

let addComment: (formData: FormData) => Promise<void>;

before(async (t) => {
  t.mock.module('next/cache', {
    namedExports: {
      revalidatePath: (path: string) => {
        state.revalidated.push(path);
      },
    },
  });
  t.mock.module('next/navigation', {
    namedExports: {
      redirect: (url: string) => {
        throw new Error(`REDIRECT ${url}`);
      },
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

  const mod = await import('../app/requests/[id]/actions');
  addComment = mod.addComment;
});

function reset(authenticated = true) {
  state.user = authenticated ? { id: 'u1', email: 'test@whub.fr' } : null;
  state.allowed = { email: 'test@whub.fr', role: 'member' };
  state.request = {
    id: 'req1',
    created_by: 'u1',
    current_version_id: 'v1',
    status: 'ready',
  };
  state.currentVersion = {
    id: 'v1',
    version_number: 1,
    qa_status: 'passed',
  };
  state.commentInsert = null;
  state.requestUpdate = null;
  state.eventInsert = null;
  state.revalidated = [];
}

function makeForm(requestId = 'req1', body = 'Passe en V2 en aérant la page 2.') {
  const form = new FormData();
  form.set('request_id', requestId);
  form.set('body', body);
  return form;
}

test('addComment — records a revision request linked to the current version', async () => {
  reset();

  await addComment(makeForm());

  assert.deepEqual(state.commentInsert, {
    request_id: 'req1',
    version_id: 'v1',
    author_id: 'u1',
    body: 'Passe en V2 en aérant la page 2.',
    comment_type: 'revision',
  });
  assert.equal(state.requestUpdate?.status, 'revision_requested');
  assert.equal(state.requestUpdate?.worker_locked_at, null);
  assert.equal(state.requestUpdate?.worker_locked_by, null);
  assert.equal(typeof state.requestUpdate?.updated_at, 'string');
  assert.equal(state.eventInsert?.event_type, 'revision_requested');
  const payload = state.eventInsert?.payload as Record<string, unknown> | undefined;
  assert.equal(payload?.source_reused, true);
  assert.equal(payload?.version_id, 'v1');
  assert.equal(payload?.version_number, 1);
  assert.equal(payload?.qa_status, 'passed');
  assert.equal(payload?.from_status, 'ready');
  assert.deepEqual(state.revalidated, ['/requests/req1', '/dashboard']);
});

test('addComment — ignores blank messages', async () => {
  reset();

  await addComment(makeForm('req1', '   '));

  assert.equal(state.commentInsert, null);
  assert.equal(state.requestUpdate, null);
  assert.equal(state.eventInsert, null);
  assert.deepEqual(state.revalidated, []);
});

test('addComment — rejects unauthenticated users', async () => {
  reset(false);
  await assert.rejects(() => addComment(makeForm()), /Not allowed|Not authenticated/);
});
