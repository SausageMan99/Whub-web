-- 011_claim_rpc_fix.sql
-- Requeue failed CV requests that are stuck with an empty candidate_first_name
-- and exhausted worker_attempts before running the normal claim logic.

create or replace function public.claim_next_cv_request(worker_name text)
returns setof public.cv_requests
language plpgsql
security definer
set search_path = public
as $$
begin
  update public.cv_requests
  set
    status = 'submitted',
    worker_locked_at = null,
    worker_locked_by = null,
    worker_attempts = 0,
    last_error = null,
    updated_at = now()
  where status = 'failed'
    and candidate_first_name = ''
    and worker_attempts >= 3;

  return query
  update public.cv_requests r
  set
    status = 'processing',
    worker_locked_at = now(),
    worker_locked_by = worker_name,
    worker_attempts = r.worker_attempts + 1,
    started_at = coalesce(r.started_at, now()),
    updated_at = now()
  where r.id = (
    select id
    from public.cv_requests
    where status in ('submitted', 'revision_requested')
      and (worker_locked_at is null or worker_locked_at < now() - interval '30 minutes')
      and worker_attempts < 3
    order by
      case priority when 'urgent' then 0 when 'high' then 1 else 2 end,
      created_at asc
    for update skip locked
    limit 1
  )
  returning r.*;
end;
$$;

grant execute on function public.claim_next_cv_request(worker_name text) to whub_worker;

-- Migration-time verification: failed jobs with candidate_first_name='' and
-- worker_attempts>=3 must be requeued to submitted and then claimed.
do $$
declare
  test_user_id uuid := '00000000-0000-4000-8000-000000001109'::uuid;
  test_request_id uuid := '00000000-0000-4000-8000-000000001119'::uuid;
  claimed public.cv_requests%rowtype;
begin
  insert into auth.users (id, email, encrypted_password, email_confirmed_at, created_at, updated_at, aud, role)
  values (
    test_user_id,
    'claim-rpc-fix-migration-test@example.invalid',
    'migration-test',
    now(),
    now(),
    now(),
    'authenticated',
    'authenticated'
  )
  on conflict (id) do nothing;

  insert into public.profiles (id, email, full_name, role)
  values (test_user_id, 'claim-rpc-fix-migration-test@example.invalid', 'Claim RPC Fix Test', 'admin')
  on conflict (id) do nothing;

  insert into public.cv_requests (
    id,
    created_by,
    title,
    candidate_first_name,
    source_file_path,
    source_file_name,
    source_file_mime,
    source_file_size,
    priority,
    status,
    worker_locked_at,
    worker_locked_by,
    worker_attempts,
    last_error,
    submitted_at,
    created_at,
    updated_at
  )
  values (
    test_request_id,
    test_user_id,
    'Claim RPC fix migration test',
    '',
    'claim-rpc-fix-test/source.pdf',
    'source.pdf',
    'application/pdf',
    1,
    'urgent',
    'failed',
    now() - interval '1 hour',
    'migration-test-worker',
    3,
    'candidate_first_name was empty',
    now() - interval '2 hours',
    now() - interval '2 hours',
    now() - interval '1 hour'
  )
  on conflict (id) do update
  set candidate_first_name = '',
      priority = 'urgent',
      status = 'failed',
      worker_locked_at = now() - interval '1 hour',
      worker_locked_by = 'migration-test-worker',
      worker_attempts = 3,
      last_error = 'candidate_first_name was empty',
      submitted_at = now() - interval '2 hours',
      created_at = now() - interval '2 hours',
      updated_at = now() - interval '1 hour';

  select *
    into claimed
  from public.claim_next_cv_request('claim-rpc-fix-verifier')
  limit 1;

  if claimed.id is distinct from test_request_id then
    raise exception 'claim_next_cv_request failed to requeue empty-name failed job: expected %, got %',
      test_request_id,
      claimed.id;
  end if;

  if claimed.status <> 'processing'
     or claimed.worker_attempts <> 1
     or claimed.worker_locked_by <> 'claim-rpc-fix-verifier' then
    raise exception 'claim_next_cv_request requeue verification failed: status %, attempts %, worker %',
      claimed.status,
      claimed.worker_attempts,
      claimed.worker_locked_by;
  end if;

  delete from public.cv_events where request_id = test_request_id;
  delete from public.cv_comments where request_id = test_request_id;
  update public.cv_requests set current_version_id = null where id = test_request_id;
  delete from public.cv_versions where request_id = test_request_id;
  delete from public.cv_requests where id = test_request_id;
  delete from public.profiles where id = test_user_id;
  delete from auth.users where id = test_user_id;
end
$$;
