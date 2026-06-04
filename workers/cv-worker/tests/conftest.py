"""Shared pytest environment defaults for worker tests.

The worker now refuses to import without WORKER_DB_URL so tests cannot
accidentally exercise the former service_role_key fallback path.
"""

import os

os.environ.setdefault("SUPABASE_URL", "https://example.supabase.co")
os.environ.setdefault("SUPABASE_ANON_KEY", "test-anon-key")
os.environ.setdefault(
    "WORKER_DB_URL",
    "postgresql://whub_worker:test@localhost:5432/postgres",
)
