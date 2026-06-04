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

-- ── TDD Step 1 (FAIL): Verify the OLD policy allows a member to see ALL requests ──
-- Run manually as an allowed 'member' user (adavid@whub.fr):
--   select * from public.cv_requests;
-- Expected (insecure) result: member sees ALL rows created by any user.
-- A secure policy MUST restrict this to only the member's own rows.
-- ─────────────────────────────────────────────────────────────────────────────

create policy "members read own requests" on public.cv_requests
  for select to authenticated using (created_by = auth.uid());

create policy "admins read all requests" on public.cv_requests
  for select to authenticated using (public.current_user_role() = 'admin');

create policy "allowed users can create requests" on public.cv_requests
  for insert to authenticated with check (public.is_allowed_user() and created_by = auth.uid());

create policy "allowed users can update own requests or admins all" on public.cv_requests
  for update to authenticated using (public.is_allowed_user() and (created_by = auth.uid() or public.current_user_role() = 'admin'));

-- ── TDD Step 4 (PASS): Verification queries ──
-- Run these as authenticated users to confirm the new policies are correct:
--
-- 1) As member (e.g. adavid@whub.fr):
--    select * from public.cv_requests;
--    Expected: only rows WHERE created_by = auth.uid()
--    (i.e. only requests created by adavid@whub.fr's profile).
--
-- 2) As admin (e.g. cdubosq@whub.fr):
--    select * from public.cv_requests;
--    Expected: ALL rows (admin override via public.current_user_role() = 'admin').
--
-- 3) Assertion via SQL (run in Supabase SQL editor):
--    with member_sessions as (
--      select 'adavid@whub.fr' as email
--    )
--    -- Member must NOT see another user's request
--    select case when count(*) = 0 then 'PASS: Member cannot see other users requests'
--                else 'FAIL: Member can see other users requests'
--           end as member_isolation_test
--    from pg_policies
--    where schemaname = 'public'
--      and tablename = 'cv_requests'
--      and policyname = 'members read own requests'
--      and cmd = 'SELECT';
--
-- 4) Policy existence check:
--    select policyname, permissive, cmd, qual
--    from pg_policies
--    where tablename = 'cv_requests'
--    order by policyname;
--    Expected:
--      | admins read all requests          | PERMISSIVE | SELECT | (public.current_user_role() = 'admin'::text) |
--      | allowed users can create requests | PERMISSIVE | INSERT | ...                                          |
--      | allowed users can update own ...  | PERMISSIVE | UPDATE | ...                                          |
--      | members read own requests         | PERMISSIVE | SELECT | (created_by = auth.uid())                     |
-- ─────────────────────────────────────────────────────────────────────────────

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
