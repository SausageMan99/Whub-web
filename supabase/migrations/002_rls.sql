create or replace function public.is_allowed_user()
returns boolean
language sql
stable
security definer
set search_path = public
as $$
  select exists (
    select 1 from public.allowed_users au
    where lower(au.email) = lower(coalesce(auth.jwt()->>'email', ''))
  );
$$;

create or replace function public.current_user_role()
returns text
language sql
stable
security definer
set search_path = public
as $$
  select coalesce((select role from public.allowed_users au where lower(au.email)=lower(coalesce(auth.jwt()->>'email',''))), 'none');
$$;

alter table public.allowed_users enable row level security;
alter table public.profiles enable row level security;
alter table public.cv_requests enable row level security;
alter table public.cv_versions enable row level security;
alter table public.cv_comments enable row level security;
alter table public.cv_events enable row level security;

create policy "allowed users can read allowed_users" on public.allowed_users
  for select to authenticated using (public.is_allowed_user());

create policy "allowed users can read profiles" on public.profiles
  for select to authenticated using (public.is_allowed_user());

create policy "allowed users can upsert own profile" on public.profiles
  for insert to authenticated with check (public.is_allowed_user() and id = auth.uid());

create policy "members read own requests" on public.cv_requests
  for select to authenticated using (created_by = auth.uid());

create policy "admins read all requests" on public.cv_requests
  for select to authenticated using (public.current_user_role() = 'admin');

create policy "allowed users can create requests" on public.cv_requests
  for insert to authenticated with check (public.is_allowed_user() and created_by = auth.uid());

create policy "allowed users can update own requests or admins all" on public.cv_requests
  for update to authenticated using (public.is_allowed_user() and (created_by = auth.uid() or public.current_user_role() = 'admin'));

create policy "admins can delete requests" on public.cv_requests
  for delete to authenticated using (public.current_user_role() = 'admin');

-- RLS verification: cv_requests members may read only their own requests;
-- admins may read all requests. These assertions intentionally run during
-- `supabase db reset --linked` so regressions fail migration replay.
do $$
begin
  insert into public.allowed_users (email, role) values
    ('rls-member@example.test', 'member'),
    ('rls-other@example.test', 'member'),
    ('rls-admin@example.test', 'admin')
  on conflict (email) do update set role = excluded.role;

  insert into auth.users (id, aud, role, email, email_confirmed_at, created_at, updated_at, raw_app_meta_data, raw_user_meta_data)
  values
    ('00000000-0000-4000-8000-000000000201', 'authenticated', 'authenticated', 'rls-member@example.test', now(), now(), now(), '{}'::jsonb, '{}'::jsonb),
    ('00000000-0000-4000-8000-000000000202', 'authenticated', 'authenticated', 'rls-other@example.test', now(), now(), now(), '{}'::jsonb, '{}'::jsonb),
    ('00000000-0000-4000-8000-000000000203', 'authenticated', 'authenticated', 'rls-admin@example.test', now(), now(), now(), '{}'::jsonb, '{}'::jsonb)
  on conflict (id) do update set email = excluded.email, updated_at = now();

  insert into public.profiles (id, email, full_name, role)
  values
    ('00000000-0000-4000-8000-000000000201', 'rls-member@example.test', 'RLS Member', 'member'),
    ('00000000-0000-4000-8000-000000000202', 'rls-other@example.test', 'RLS Other', 'member'),
    ('00000000-0000-4000-8000-000000000203', 'rls-admin@example.test', 'RLS Admin', 'admin')
  on conflict (id) do update set email = excluded.email, role = excluded.role;

  insert into public.cv_requests (id, created_by, title, source_file_path, source_file_name)
  values
    ('00000000-0000-4000-8000-000000000301', '00000000-0000-4000-8000-000000000201', 'RLS member-owned request', 'rls/member.pdf', 'member.pdf'),
    ('00000000-0000-4000-8000-000000000302', '00000000-0000-4000-8000-000000000202', 'RLS other-owned request', 'rls/other.pdf', 'other.pdf')
  on conflict (id) do update set created_by = excluded.created_by, title = excluded.title;
end $$;

set role authenticated;
select set_config(
  'request.jwt.claims',
  '{"sub":"00000000-0000-4000-8000-000000000201","email":"rls-member@example.test","role":"authenticated"}',
  true
);
do $$
declare
  visible_count integer;
begin
  select count(*) into visible_count
  from public.cv_requests
  where id in ('00000000-0000-4000-8000-000000000301', '00000000-0000-4000-8000-000000000302');

  if visible_count <> 1 then
    raise exception 'cv_requests RLS regression: member saw % test requests, expected 1 own request', visible_count;
  end if;
end $$;

select set_config(
  'request.jwt.claims',
  '{"sub":"00000000-0000-4000-8000-000000000203","email":"rls-admin@example.test","role":"authenticated"}',
  true
);
do $$
declare
  visible_count integer;
begin
  select count(*) into visible_count
  from public.cv_requests
  where id in ('00000000-0000-4000-8000-000000000301', '00000000-0000-4000-8000-000000000302');

  if visible_count <> 2 then
    raise exception 'cv_requests RLS regression: admin saw % test requests, expected all 2 test requests', visible_count;
  end if;
end $$;
set role postgres;

-- Remove assertion fixtures so replay verification leaves no application data.
delete from public.cv_requests
where id in ('00000000-0000-4000-8000-000000000301', '00000000-0000-4000-8000-000000000302');

delete from public.profiles
where id in ('00000000-0000-4000-8000-000000000201', '00000000-0000-4000-8000-000000000202', '00000000-0000-4000-8000-000000000203');

delete from auth.users
where id in ('00000000-0000-4000-8000-000000000201', '00000000-0000-4000-8000-000000000202', '00000000-0000-4000-8000-000000000203');

delete from public.allowed_users
where email in ('rls-member@example.test', 'rls-other@example.test', 'rls-admin@example.test');

create policy "allowed users can read versions" on public.cv_versions
  for select to authenticated using (public.is_allowed_user());

create policy "allowed users can read comments" on public.cv_comments
  for select to authenticated using (public.is_allowed_user());

create policy "allowed users can create comments" on public.cv_comments
  for insert to authenticated with check (public.is_allowed_user() and author_id = auth.uid());

create policy "allowed users can update own comments or admins" on public.cv_comments
  for update to authenticated using (public.is_allowed_user() and (author_id = auth.uid() or public.current_user_role() = 'admin'));

create policy "allowed users can read events" on public.cv_events
  for select to authenticated using (public.is_allowed_user());

create policy "admins can delete versions" on public.cv_versions
  for delete to authenticated using (public.current_user_role() = 'admin');

create policy "admins can delete comments" on public.cv_comments
  for delete to authenticated using (public.current_user_role() = 'admin');

create policy "admins can delete events" on public.cv_events
  for delete to authenticated using (public.current_user_role() = 'admin');
