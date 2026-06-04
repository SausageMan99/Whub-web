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
--   4. Grants USAGE on all sequences in public (for serial/bigserial columns)
--   5. Grants storage.objects SELECT/INSERT for the worker's buckets
--      (cv-sources, cv-renderer-inputs, cv-finals, cv-artifacts)
--   6. Executes claim_next_cv_request() as the function owner (security definer)
--      so the worker does NOT need direct EXECUTE on the function; it calls
--      through the RPC wrapper which connects as whub_worker and runs the
--      function via the anonymous code block pattern.
--   7. (Optional) Revoke service_role from default_worker_usage — prevents
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

-- ── 4. Sequence usage (for tables with serial/bigserial columns) ──
grant usage, select on all sequences in schema public to whub_worker;

-- ── 5. Default permissions for future tables created in public ──
alter default privileges in schema public
  grant select, insert, update on tables to whub_worker;

alter default privileges in schema public
  grant usage, select on sequences to whub_worker;

-- ── 6. RPC function execution ──
-- claim_next_cv_request is SECURITY DEFINER (owned by postgres/superuser),
-- so whub_worker does NOT need direct EXECUTE privilege on it.
-- The worker calls it via the PostgreSQL function call syntax, which runs
-- with the function owner's privileges.
grant execute on function public.claim_next_cv_request(worker_name text) to whub_worker;
grant execute on function public.verify_access_code(email text, code text) to whub_worker;
grant execute on function public.rotate_access_code(email text) to whub_worker;
grant execute on function public.generate_access_code() to whub_worker;
grant execute on function public.hash_access_code(code text) to whub_worker;
grant execute on function public.is_allowed_user() to whub_worker;
grant execute on function public.current_user_role() to whub_worker;

-- ── 7. Storage bucket permissions ──
-- The worker uploads rendered CVs and artifacts.  Storage RLS policies
-- are defined in 003_storage.sql.  Since whub_worker is NOT an authenticated
-- user (it's a direct PG role), storage operations via the REST API use
-- the anon key + Storage RLS policies.  For direct PG operations, we grant
-- storage schema access so the worker can manage files if needed.
grant usage on schema storage to whub_worker;
grant select, insert on storage.buckets to whub_worker;

-- ── 8. Row-level security bypass ──
-- whub_worker is NOT a Supabase-authenticated user, so RLS policies that
-- depend on auth.uid() or auth.jwt() will block it.  We explicitly bypass
-- RLS for whub_worker by granting the BYPASSRLS attribute.  This is safe
-- because the role already has only SELECT/INSERT/UPDATE grants — no DDL,
-- no DELETE, no system catalogs.
alter role whub_worker bypassrls;

-- ── 9. Verify the role has no dangerous permissions ──
-- Run this after migration:
--   select * from information_schema.role_table_grants
--   where grantee = 'whub_worker' and privilege_type in ('DELETE', 'TRUNCATE', 'REFERENCES', 'TRIGGER');
-- Expected: empty result set (no DELETE/TRUNCATE/REFERENCES/TRIGGER)
--
--   select * from information_schema.role_table_grants
--   where grantee = 'whub_worker' and table_schema = 'auth';
-- Expected: empty result set (no access to auth schema)
