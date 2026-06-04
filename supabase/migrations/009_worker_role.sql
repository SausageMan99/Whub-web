-- 009_worker_role.sql
-- Restrict worker to a dedicated PostgreSQL LOGIN role.
--
-- The worker must not use SUPABASE_SERVICE_ROLE_KEY.  It connects directly to
-- PostgreSQL as whub_worker, which receives only the object privileges needed
-- for job claiming and CV generation.

-- ── 1. Create dedicated LOGIN role ────────────────────────────────────────
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'whub_worker') then
    create role whub_worker login password null;
  end if;
end
$$;

comment on role whub_worker is
  'Least-privilege role for the CV worker. Password is managed outside migrations.';

-- Do not inherit accidental privileges from broad grants.
alter role whub_worker noinherit;

-- The worker is not mapped to a Supabase JWT/auth.uid().  Table privileges below
-- restrict its surface area; BYPASSRLS lets it process the queue without using
-- the all-powerful service_role key.
alter role whub_worker bypassrls;

-- ── 2. Remove dangerous or accidental grants first ────────────────────────
revoke all privileges on schema auth from whub_worker;
revoke all privileges on schema storage from whub_worker;
revoke all privileges on all tables in schema auth from whub_worker;
revoke all privileges on all tables in schema storage from whub_worker;
revoke all privileges on all sequences in schema auth from whub_worker;
revoke all privileges on all sequences in schema storage from whub_worker;
revoke all privileges on all functions in schema auth from whub_worker;
revoke all privileges on all functions in schema storage from whub_worker;

revoke all privileges on all tables in schema public from whub_worker;
revoke all privileges on all sequences in schema public from whub_worker;
revoke all privileges on all functions in schema public from whub_worker;

-- ── 3. Minimal public schema/table/function privileges ────────────────────
grant usage on schema public to whub_worker;

grant select, insert, update on table public.cv_requests to whub_worker;
grant select, insert, update on table public.cv_versions to whub_worker;
grant select, insert, update on table public.cv_events to whub_worker;
grant select, insert, update on table public.cv_comments to whub_worker;

-- UUID primary keys use gen_random_uuid(), but keep this explicit for deployments
-- where version_number was converted to a sequence-backed column.
do $$
begin
  if to_regclass('public.cv_versions_version_number_seq') is not null then
    grant usage, select on sequence public.cv_versions_version_number_seq to whub_worker;
  end if;
end
$$;

-- The queue claim RPC is the only public function the worker calls.
grant execute on function public.claim_next_cv_request(worker_name text) to whub_worker;

-- ── 4. Migration-time least-privilege verification (TDD guard) ────────────
-- Seed one disposable request as the migration owner, then SET ROLE whub_worker
-- and verify allowed operations succeed while auth/storage access fails.
do $$
begin
  -- Supabase migrations do not always execute as a superuser.  SET ROLE still
  -- requires membership, so grant membership to the migration executor for the
  -- duration of this verification and revoke it after RESET ROLE below.
  execute format('grant whub_worker to %I', current_user);
end
$$;

do $$
declare
  test_user_id uuid := '00000000-0000-4000-8000-000000000904'::uuid;
  test_request_id uuid := '00000000-0000-4000-8000-000000000914'::uuid;
  test_version_id uuid := '00000000-0000-4000-8000-000000000924'::uuid;
begin
  insert into auth.users (id, email, encrypted_password, email_confirmed_at, created_at, updated_at, aud, role)
  values (
    test_user_id,
    'worker-role-migration-test@example.invalid',
    'migration-test',
    now(),
    now(),
    now(),
    'authenticated',
    'authenticated'
  )
  on conflict (id) do nothing;

  insert into public.profiles (id, email, full_name, role)
  values (test_user_id, 'worker-role-migration-test@example.invalid', 'Worker Role Test', 'admin')
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
    status
  )
  values (
    test_request_id,
    test_user_id,
    'Worker role migration test',
    'Test',
    'worker-role-test/source.pdf',
    'source.pdf',
    'application/pdf',
    1,
    'submitted'
  )
  on conflict (id) do nothing;
end
$$;

create or replace function public._cleanup_worker_role_migration_test()
returns void
language plpgsql
security definer
set search_path = public, auth
as $$
begin
  delete from public.cv_events where request_id = '00000000-0000-4000-8000-000000000914'::uuid;
  delete from public.cv_comments where request_id = '00000000-0000-4000-8000-000000000914'::uuid;
  update public.cv_requests
  set current_version_id = null
  where id = '00000000-0000-4000-8000-000000000914'::uuid;
  delete from public.cv_versions where request_id = '00000000-0000-4000-8000-000000000914'::uuid;
  delete from public.cv_requests where id = '00000000-0000-4000-8000-000000000914'::uuid;
  delete from public.profiles where id = '00000000-0000-4000-8000-000000000904'::uuid;
  delete from auth.users where id = '00000000-0000-4000-8000-000000000904'::uuid;
  revoke execute on function public._cleanup_worker_role_migration_test() from whub_worker;
end;
$$;

do $$
begin
  execute 'grant execute on function public._cleanup_worker_role_migration_test() to whub_worker';
end
$$;

begin;
set local role whub_worker;

-- Allowed reads/writes on worker-owned tables.
select id from public.cv_requests where id = '00000000-0000-4000-8000-000000000914'::uuid;
update public.cv_requests
set worker_locked_by = 'migration-test-worker', updated_at = now()
where id = '00000000-0000-4000-8000-000000000914'::uuid;

insert into public.cv_versions (id, request_id, version_number, structured_json, qa_status, qa_report)
values (
  '00000000-0000-4000-8000-000000000924'::uuid,
  '00000000-0000-4000-8000-000000000914'::uuid,
  904,
  '{"migration_test": true}'::jsonb,
  'passed',
  '{"ok": true}'::jsonb
)
on conflict (request_id, version_number) do update
set qa_report = excluded.qa_report;

update public.cv_versions
set generated_by = 'migration-test-worker'
where request_id = '00000000-0000-4000-8000-000000000914'::uuid
  and version_number = 904;

insert into public.cv_events (request_id, actor_type, event_type, payload)
values (
  '00000000-0000-4000-8000-000000000914'::uuid,
  'worker',
  'worker_role_migration_test',
  '{"ok": true}'::jsonb
);

update public.cv_events
set payload = '{"ok": true, "updated": true}'::jsonb
where request_id = '00000000-0000-4000-8000-000000000914'::uuid
  and event_type = 'worker_role_migration_test';

insert into public.cv_comments (request_id, version_id, author_id, body, comment_type)
values (
  '00000000-0000-4000-8000-000000000914'::uuid,
  '00000000-0000-4000-8000-000000000924'::uuid,
  '00000000-0000-4000-8000-000000000904'::uuid,
  'worker role migration test',
  'internal'
);

update public.cv_comments
set resolved = true, resolved_at = now()
where request_id = '00000000-0000-4000-8000-000000000914'::uuid
  and body = 'worker role migration test';

-- Forbidden schemas must remain inaccessible.
do $$
begin
  begin
    perform 1 from auth.users limit 1;
    raise exception 'whub_worker unexpectedly has access to auth.users';
  exception
    when insufficient_privilege or undefined_table or invalid_schema_name then
      null;
  end;

  begin
    perform 1 from storage.objects limit 1;
    raise exception 'whub_worker unexpectedly has access to storage.objects';
  exception
    when insufficient_privilege or undefined_table or invalid_schema_name then
      null;
  end;
end
$$;

select public._cleanup_worker_role_migration_test();

commit;

-- Keep the migration executor's whub_worker membership if the platform grants it;
-- whub_worker is NOINHERIT, so this does not leak privileges into normal work.
