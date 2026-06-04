-- 008_worker_role.sql
-- Restrict worker to dedicated PostgreSQL role (no service_role_key)
--
-- WHY:
--   The worker previously connected via SUPABASE_SERVICE_ROLE_KEY, which grants
--   full admin access (bypasses RLS, can drop tables, alter schema, access
--   auth.users, etc.).  This is a privilege-escalation risk if the worker is
--   ever compromised.
--
-- WHAT THIS DOES:
--   1. Creates role whub_worker with LOGIN (password set via environment)
--   2. Grants USAGE on schema public
--   3. Grants SELECT, INSERT, UPDATE on cv_requests, cv_versions, cv_comments, cv_events
--      (worker never needs DELETE or DDL)
--   4. Grants USAGE only on sequences owned by the CV tables (if any)
--   5. Grants EXECUTE only on claim_next_cv_request(), the only RPC the worker calls.
--   6. Storage remains behind Supabase Storage REST + anon key/RLS;
--      whub_worker is not granted direct storage schema/table access.
--   7. claim_next_cv_request() runs as its function owner (SECURITY DEFINER)
--      after whub_worker is allowed to invoke it.
--   8. (Optional) Revoke service_role from default_worker_usage — prevents
--      accidental grants to public/authenticated that would leak to worker.
--
-- REVERSIBLE:
--   To rollback: DROP ROLE IF EXISTS whub_worker;
--
-- NOTE:
--   whub_worker is a LOGIN role, NOT a NOLOGIN role.  NOLOGIN roles cannot
--   open direct PostgreSQL connections.  Since the worker connects via
--   psycopg2 with a connection string, it needs LOGIN.
--   Set the password via environment variable WORKER_DB_PASSWORD or embed
--   it in the connection string.
--
-- CONNECTION STRING FORMAT:
--   postgresql://whub_worker:<password>@<host>:6543/postgres?pgbouncer=true
--   (port 6543 is Supabase's PgBouncer transaction mode; use 5432 for session mode)
-- ─────────────────────────────────────────────────────────────────────────────

-- ── 1. Create the dedicated role ──
do $$
begin
  if not exists (select 1 from pg_roles where rolname = 'whub_worker') then
    create role whub_worker login
      -- Password is set via ALTER ROLE in a separate step or environment
      -- Password will be injected via Supabase dashboard or Terraform
      password null;
  end if;
end
$$;

-- ── 2. Schema access ──
grant usage on schema public to whub_worker;

-- ── 3. Table-level permissions (SELECT, INSERT, UPDATE only — no DELETE, no DDL) ──
grant select, insert, update on public.cv_requests   to whub_worker;
grant select, insert, update on public.cv_versions    to whub_worker;
grant select, insert, update on public.cv_comments    to whub_worker;
grant select, insert, update on public.cv_events      to whub_worker;

-- ── 4. Sequence usage (only sequences owned by CV tables, if any) ──
do $$
declare
  seq regclass;
begin
  for seq in
    select pg_get_serial_sequence(format('%I.%I', n.nspname, c.relname), a.attname)::regclass
    from pg_class c
    join pg_namespace n on n.oid = c.relnamespace
    join pg_attribute a on a.attrelid = c.oid
    where n.nspname = 'public'
      and c.relname in ('cv_requests', 'cv_versions', 'cv_comments', 'cv_events')
      and a.attnum > 0
      and not a.attisdropped
      and pg_get_serial_sequence(format('%I.%I', n.nspname, c.relname), a.attname) is not null
  loop
    execute format('grant usage, select on sequence %s to whub_worker', seq);
  end loop;
end
$$;

-- ── 5. RPC function execution ──
-- claim_next_cv_request is SECURITY DEFINER (owned by postgres/superuser),
-- and is the only RPC function the worker calls.
grant execute on function public.claim_next_cv_request(worker_name text) to whub_worker;

-- ── 6. Storage bucket permissions ──
-- The worker downloads/uploads files through the Supabase Storage REST API
-- using SUPABASE_ANON_KEY.  Do not grant the direct PostgreSQL whub_worker
-- role storage schema/table privileges here; Storage access remains governed
-- by storage RLS policies.

-- ── 7. Row-level security bypass ──
-- whub_worker is NOT a Supabase-authenticated user, so RLS policies that
-- depend on auth.uid() or auth.jwt() will block it.  We explicitly bypass
-- RLS for whub_worker by granting the BYPASSRLS attribute.  This is safe
-- because the role already has only SELECT/INSERT/UPDATE grants — no DDL,
-- no DELETE, no system catalogs.
alter role whub_worker bypassrls;

-- ── 8. Verify the role has no dangerous permissions ──
-- Run this after migration:
--   select * from information_schema.role_table_grants
--   where grantee = 'whub_worker' and privilege_type in ('DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER');
-- Expected: empty result set (no DELETE/TRUNCATE/REFERENCES/TRIGGER)
--
--   select * from information_schema.role_table_grants
--   where grantee = 'whub_worker' and table_schema = 'auth';
-- Expected: empty result set (no access to auth schema)
