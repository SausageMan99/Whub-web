-- Auth désactivé — l'upload worker vers cv-renderer-inputs passe par REST (clé anon)
create policy "public can write renderer inputs" on storage.objects
  for insert to anon
  with check (bucket_id = 'cv-renderer-inputs');

create policy "public can read renderer inputs" on storage.objects
  for select to anon
  using (bucket_id = 'cv-renderer-inputs');
