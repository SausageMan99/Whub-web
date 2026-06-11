-- Storage owner-based policies (replaces anon policies from 003 + 014)
-- Owner is stored in metadata.owner on storage.objects
-- Authenticated users: can INSERT/SELECT own objects (metadata.owner = auth.uid())
-- Service role (worker, admin APIs): bypasses RLS entirely
-- Signed URLs: bypass RLS via JWT in URL
-- Anon access: REMOVED completely

-- Drop anon policies from migration 014
drop policy if exists "public can write renderer inputs" on storage.objects;
drop policy if exists "public can read renderer inputs" on storage.objects;
drop policy if exists "public can write finals" on storage.objects;
drop policy if exists "public can read finals" on storage.objects;
drop policy if exists "public can write artifacts" on storage.objects;
drop policy if exists "public can read artifacts" on storage.objects;

-- Drop legacy authenticated policies from migration 003 (replaced by owner-based)
drop policy if exists "allowed users can read cv storage" on storage.objects;
drop policy if exists "allowed users can upload cv sources" on storage.objects;

-- Owner-based INSERT policy: user can insert if they set metadata.owner = auth.uid()
create policy "owners can insert own objects" on storage.objects
  for insert to authenticated
  with check (
    bucket_id in ('cv-sources','cv-renderer-inputs','cv-finals','cv-artifacts')
    and (metadata->>'owner') = auth.uid()::text
  );

-- Owner-based SELECT policy: user can read if metadata.owner = auth.uid()
-- Signed URLs and service role bypass RLS automatically
create policy "owners can read own objects" on storage.objects
  for select to authenticated
  using (
    bucket_id in ('cv-sources','cv-renderer-inputs','cv-finals','cv-artifacts')
    and (metadata->>'owner') = auth.uid()::text
  );

-- Owner-based UPDATE policy: user can update metadata on own objects
create policy "owners can update own objects" on storage.objects
  for update to authenticated
  using (
    bucket_id in ('cv-sources','cv-renderer-inputs','cv-finals','cv-artifacts')
    and (metadata->>'owner') = auth.uid()::text
  )
  with check (
    bucket_id in ('cv-sources','cv-renderer-inputs','cv-finals','cv-artifacts')
    and (metadata->>'owner') = auth.uid()::text
  );

-- Owner-based DELETE policy: user can delete own objects
create policy "owners can delete own objects" on storage.objects
  for delete to authenticated
  using (
    bucket_id in ('cv-sources','cv-renderer-inputs','cv-finals','cv-artifacts')
    and (metadata->>'owner') = auth.uid()::text
  );