import test, { before } from 'node:test';
import assert from 'node:assert/strict';

let state = {
  user: { id: 'u1', email: 'test@whub.fr' } as { id: string; email: string } | null,
  allowed: { email: 'test@whub.fr', role: 'admin' } as { email: string; role: string } | null,
  request: { id: 'req1', status: 'failed', created_by: 'u1' } as { id: string; status: string; created_by: string } | null,
  updatedPayload: null as Record<string, unknown> | null,
  updatedId: null as string | null,
  updatedStatuses: null as string[] | null,
  updateError: null as Error | null,
  updatedRows: [{ id: 'req1' }] as { id: string }[] | null,
  insertedEvent: null as Record<string, unknown> | null,
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
            state.updatedPayload = payload;
            return {
              eq(_field: string, id: string) {
                state.updatedId = id;
                return {
                  in(_field2: string, statuses: string[]) {
                    state.updatedStatuses = statuses;
                    return {
                      select() {
                        return Promise.resolve({ data: state.updatedRows, error: state.updateError });
                      },
                    };
                  },
                };
              },
            };
          },
        };
      }
      if (table === 'cv_events') {
        return {
          insert(payload: Record<string, unknown>) {
            state.insertedEvent = payload;
            return Promise.resolve({ error: null });
          },
        };
      }
      return {};
    },
  };
}

let retryRequest: (formData: FormData) => Promise<void>;

before(async (t) => {
  t.mock.module('next/cache', {
    namedExports: {
      revalidatePath: (path: string) => {
        state.revalidated.push(path);
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
  retryRequest = mod.retryRequest;
});

function reset(authenticated = true) {
  state.user = authenticated ? { id: 'u1', email: 'test@whub.fr' } : null;
  state.allowed = { email: 'test@whub.fr', role: 'admin' };
  state.request = { id: 'req1', status: 'failed', created_by: 'u1' };
  state.updatedPayload = null;
  state.updatedId = null;
  state.updatedStatuses = null;
  state.updateError = null;
  state.updatedRows = [{ id: 'req1' }];
  state.insertedEvent = null;
  state.revalidated = [];
}

function makeForm(requestId = 'req1') {
  const form = new FormData();
  form.set('request_id', requestId);
  return form;
}

test('retryRequest — resets failed request into submitted queue', async () => {
  reset();
  await retryRequest(makeForm('req-retry'));

  assert.equal(state.updatedId, 'req-retry');
  assert.deepEqual(state.updatedStatuses, ['failed', 'qa_failed']);
  assert.equal(state.updatedPayload?.status, 'submitted');
  assert.equal(state.updatedPayload?.last_error, null);
  assert.equal(state.updatedPayload?.worker_locked_at, null);
  assert.equal(state.updatedPayload?.worker_locked_by, null);
  assert.equal(state.updatedPayload?.worker_attempts, 0);
  assert.equal(state.insertedEvent?.request_id, 'req-retry');
  assert.equal(state.insertedEvent?.event_type, 'retry_requested');
  assert.deepEqual(state.revalidated, ['/requests/req-retry', '/dashboard']);
});

test('retryRequest — rejects unauthenticated users', async () => {
  reset(false);
  await assert.rejects(() => retryRequest(makeForm()), /Not authenticated/);
});

test('retryRequest — blocks non-whitelisted users', async () => {
  reset();
  state.allowed = null;
  await assert.rejects(() => retryRequest(makeForm()), /Not allowed/);
});

test('retryRequest — blocks non-owner members from retrying arbitrary requests', async () => {
  reset();
  state.allowed = { email: 'test@whub.fr', role: 'member' };
  state.request = { id: 'req1', status: 'failed', created_by: 'other-user' };

  await assert.rejects(() => retryRequest(makeForm('req1')), /Forbidden/);
  assert.equal(state.updatedPayload, null);
  assert.equal(state.insertedEvent, null);
});

test('retryRequest — does not emit event when request is not retryable', async () => {
  reset();
  state.request = { id: 'req1', status: 'ready', created_by: 'u1' };

  await assert.rejects(() => retryRequest(makeForm('req1')), /not retryable/);
  assert.equal(state.updatedPayload, null);
  assert.equal(state.insertedEvent, null);
});

test('retryRequest — does not emit event when guarded update affects zero rows', async () => {
  reset();
  state.updatedRows = [];

  await assert.rejects(() => retryRequest(makeForm('req1')), /Retry failed/);
  assert.equal(state.insertedEvent, null);
});
