-- 010_version_sequence.sql
-- Make cv_versions.version_number atomic by backing it with a PostgreSQL sequence.

create sequence if not exists public.cv_versions_version_number_seq
  as integer
  start with 1
  increment by 1
  no minvalue
  no maxvalue
  cache 1;

alter sequence public.cv_versions_version_number_seq
  owned by public.cv_versions.version_number;

select setval(
  'public.cv_versions_version_number_seq',
  greatest(coalesce((select max(version_number) from public.cv_versions), 0) + 1, 1),
  false
);

alter table public.cv_versions
  alter column version_number set default nextval('public.cv_versions_version_number_seq'::regclass);

grant usage, select on sequence public.cv_versions_version_number_seq to whub_worker;

-- Migration-time verification: inserting two versions without version_number must
-- allocate atomic version numbers automatically. On a clean reset these are 1 and 2;
-- on an existing database they start after the pre-migration maximum.
do $$
declare
  test_user_id uuid := '00000000-0000-4000-8000-000000001006'::uuid;
  test_request_id uuid := '00000000-0000-4000-8000-000000001016'::uuid;
  expected_start int := greatest(coalesce((select max(version_number) from public.cv_versions), 0) + 1, 1);
  version_numbers int[];
begin
  insert into auth.users (id, email, encrypted_password, email_confirmed_at, created_at, updated_at, aud, role)
  values (
    test_user_id,
    'version-sequence-migration-test@example.invalid',
    'migration-test',
    now(),
    now(),
    now(),
    'authenticated',
    'authenticated'
  )
  on conflict (id) do nothing;

  insert into public.profiles (id, email, full_name, role)
  values (test_user_id, 'version-sequence-migration-test@example.invalid', 'Version Sequence Test', 'admin')
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
    'Version sequence migration test',
    'Test',
    'version-sequence-test/source.pdf',
    'source.pdf',
    'application/pdf',
    1,
    'submitted'
  )
  on conflict (id) do nothing;

  insert into public.cv_versions (request_id, structured_json, qa_status, qa_report)
  values
    (test_request_id, '{"migration_test": true, "ordinal": 1}'::jsonb, 'passed', '{"ok": true}'::jsonb),
    (test_request_id, '{"migration_test": true, "ordinal": 2}'::jsonb, 'passed', '{"ok": true}'::jsonb);

  select array_agg(version_number order by version_number)
    into version_numbers
  from public.cv_versions
  where request_id = test_request_id;

  if version_numbers is distinct from array[expected_start, expected_start + 1] then
    raise exception 'cv_versions.version_number DEFAULT verification failed: expected %, got %',
      array[expected_start, expected_start + 1],
      version_numbers;
  end if;

  delete from public.cv_versions where request_id = test_request_id;
  delete from public.cv_requests where id = test_request_id;
  delete from public.profiles where id = test_user_id;
  delete from auth.users where id = test_user_id;

  -- Do not let disposable verification rows burn production sequence values.
  perform setval('public.cv_versions_version_number_seq', expected_start, false);
end
$$;
