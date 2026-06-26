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
  cvComments: [] as Record<string, unknown>[],
};

class ChainBuilder {
  clauses: Array<{ column: string; value: unknown; op: string }> = [];

  eq(column: string, value: unknown) {
    this.clauses.push({ column, value, op: 'eq' });
    return this;
  }

  or(expression: string) {
    this.clauses.push({ column: expression, value: null, op: 'or' });
    return this;
  }

  is(check: string) {
    this.clauses.push({ column: check, value: null, op: 'is' });
    return this;
  }

  gte(column: string, value: unknown) {
    this.clauses.push({ column, value, op: 'gte' });
    return this;
  }

  maybeSingle() {
    const matched = state.cvComments.find((row) => {
      return this.clauses.every((clause) => {
        if (clause.op === 'eq') return row[clause.column] === clause.value;
        if (clause.op === 'gte') return String(row[clause.column]) >= String(clause.value);
        if (clause.op === 'is') return row[clause.column] === null;
        return true;
      });
    });
    return Promise.resolve({ data: matched ?? null, error: null });
  }
}

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
          select() {
            return new ChainBuilder();
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
  state.cvComments = [];
}

function makeForm(requestId = 'req1', body = 'remonter la mission page 3', category?: string) {
  const form = new FormData();
  form.set('request_id', requestId);
  form.set('body', body);
  if (category) form.set('category', category);
  return form;
}

test('test_duplicate_revision_within_window_is_suppressed', async () => {
  reset();
  const existingComment = {
    id: 'comment-1',
    request_id: 'req1',
    version_id: 'v1',
    body: 'remonter la mission page 3',
    comment_type: 'revision',
    resolved: false,
    created_at: new Date().toISOString(),
  };
  state.cvComments.push(existingComment);

  await addComment(makeForm('req1', 'remonter la mission page 3', 'other'));

  assert.equal(state.commentInsert, null, 'should not insert a new cv_comments row');
  assert.equal(state.requestUpdate, null, 'should not update cv_requests status');
  assert.equal(state.eventInsert, null, 'should not insert a new cv_events row');
  assert.deepEqual(state.revalidated, ['/requests/req1', '/dashboard']);
});

test('test_duplicate_revision_different_body_is_kept', async () => {
  reset();
  const existingComment = {
    id: 'comment-1',
    request_id: 'req1',
    version_id: 'v1',
    body: 'remonter la mission page 3',
    comment_type: 'revision',
    resolved: false,
    created_at: new Date().toISOString(),
  };
  state.cvComments.push(existingComment);

  await addComment(makeForm('req1', 'aérer la page 2', 'other'));

  assert.ok(state.commentInsert, 'should insert a new cv_comments row');
  assert.equal(state.requestUpdate?.status, 'revision_requested');
  assert.ok(state.eventInsert, 'should insert a new cv_events row');
});

test('test_duplicate_revision_outside_window_is_kept', async () => {
  reset();
  const existingComment = {
    id: 'comment-1',
    request_id: 'req1',
    version_id: 'v1',
    body: 'remonter la mission page 3',
    comment_type: 'revision',
    resolved: false,
    created_at: new Date(Date.now() - 30_000).toISOString(),
  };
  state.cvComments.push(existingComment);

  await addComment(makeForm('req1', 'remonter la mission page 3', 'other'));

  assert.ok(state.commentInsert, 'should insert a new cv_comments row');
  assert.equal(state.requestUpdate?.status, 'revision_requested');
  assert.ok(state.eventInsert, 'should insert a new cv_events row');
});
