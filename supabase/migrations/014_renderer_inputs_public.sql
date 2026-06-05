-- Auth désactivé — uploads worker vers tous les buckets via REST (clé anon)
create policy "public can write renderer inputs" on storage.objects
  for insert to anon
  with check (bucket_id = 'cv-renderer-inputs');

create policy "public can read renderer inputs" on storage.objects
  for select to anon
  using (bucket_id = 'cv-renderer-inputs');

create policy "public can write finals" on storage.objects
  for insert to anon
  with check (bucket_id = 'cv-finals');

create policy "public can read finals" on storage.objects
  for select to anon
  using (bucket_id = 'cv-finals');

create policy "public can write artifacts" on storage.objects
  for insert to anon
  with check (bucket_id = 'cv-artifacts');

create policy "public can read artifacts" on storage.objects
  for select to anon
  using (bucket_id = 'cv-artifacts');
