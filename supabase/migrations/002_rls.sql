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

create policy "allowed users can read requests" on public.cv_requests
  for select to authenticated using (public.is_allowed_user());

create policy "allowed users can create requests" on public.cv_requests
  for insert to authenticated with check (public.is_allowed_user() and created_by = auth.uid());

create policy "allowed users can update own requests or admins all" on public.cv_requests
  for update to authenticated using (public.is_allowed_user() and (created_by = auth.uid() or public.current_user_role() = 'admin'));

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
