-- Auth désactivé pour le développement/test.
-- Toutes les pages et Server Actions utilisent désormais le service_role_key
-- (createSupabaseAdminClient), qui bypass RLS. On ajoute des policies public
-- au cas où un accès anon serait nécessaire.

-- Public SELECT policies pour les pages (dashboard, detail request)
create policy "public can read cv_requests" on public.cv_requests
  for select to anon using (true);

create policy "public can read cv_versions" on public.cv_versions
  for select to anon using (true);

create policy "public can read cv_comments" on public.cv_comments
  for select to anon using (true);

create policy "public can read cv_events" on public.cv_events
  for select to anon using (true);

-- Public INSERT pour les Server Actions sans auth (creation de demande)
create policy "public can insert cv_requests" on public.cv_requests
  for insert to anon with check (true);

create policy "public can insert cv_comments" on public.cv_comments
  for insert to anon with check (true);

create policy "public can insert cv_events" on public.cv_events
  for insert to anon with check (true);

-- Public UPDATE pour les actions (revision_requested, retry)
create policy "public can update cv_requests" on public.cv_requests
  for update to anon using (true);

-- Storage: public read/download
create policy "public can read cv storage" on storage.objects
  for select to anon
  using (bucket_id in ('cv-sources','cv-finals','cv-artifacts'));

create policy "public can upload cv sources" on storage.objects
  for insert to anon
  with check (bucket_id = 'cv-sources');