insert into storage.buckets (id, name, public) values
  ('cv-sources', 'cv-sources', false),
  ('cv-renderer-inputs', 'cv-renderer-inputs', false),
  ('cv-finals', 'cv-finals', false),
  ('cv-artifacts', 'cv-artifacts', false)
on conflict (id) do nothing;

create policy "allowed users can read cv storage" on storage.objects
  for select to authenticated
  using (bucket_id in ('cv-sources','cv-finals','cv-artifacts') and public.is_allowed_user());

create policy "allowed users can upload cv sources" on storage.objects
  for insert to authenticated
  with check (bucket_id = 'cv-sources' and public.is_allowed_user());

-- Worker writes final PDFs/artifacts using SUPABASE_SERVICE_ROLE_KEY, bypassing RLS.
