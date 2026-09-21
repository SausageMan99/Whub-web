"""Shared pytest environment defaults for worker tests.

Tests must never reach a production database. The worker resolves its
PostgreSQL URL from ``worker_database_url`` (env ``WORKER_DATABASE_URL``);
``WORKER_DB_URL`` only fills the sibling field and does NOT influence the
client — incident 2026-09-21: a test called ``main()`` unmocked and the new
stale-lock reaper wrote a requeue to the live Supabase project because this
file overrode only ``WORKER_DB_URL``. Both names are now hard-set (not
setdefault) to an unreachable localhost URL, and the service-role key is
stubbed so the REST fallback cannot carry real credentials either.
"""

import os

os.environ["SUPABASE_URL"] = "https://example.supabase.co"
os.environ["SUPABASE_ANON_KEY"] = "test-anon-key"
os.environ["SUPABASE_SERVICE_ROLE_KEY"] = "test-service-role-key"
os.environ["WORKER_DATABASE_URL"] = "postgresql://whub_worker:test@localhost:5432/postgres"
os.environ["WORKER_DB_URL"] = "postgresql://whub_worker:test@localhost:5432/postgres"
