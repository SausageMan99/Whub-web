"""Guard: the pytest process must never hold production DB credentials.

Incident 2026-09-21: a worker test called ``main()`` unmocked; because only
``WORKER_DB_URL`` (the sibling-field alias) was overridden in conftest while
the client reads ``settings.worker_database_url``, the new stale-lock reaper
wrote a requeue to the live Supabase project during a full test-suite run.
These assertions keep the isolation honest — if any of them fails, STOP and
fix the environment before running the rest of the suite against it.
"""

from src.config import settings


def test_conftest_isolates_worker_database_url_from_production():
    assert "localhost:5432" in settings.worker_database_url, (
        "worker_database_url must be pinned to the unreachable localhost "
        "target in tests — it is the field the DB client actually reads"
    )
    assert "supabase.co" not in settings.worker_database_url


def test_conftest_isolates_worker_db_url_alias():
    assert "localhost:5432" in settings.worker_db_url
    assert "supabase.co" not in settings.worker_db_url


def test_conftest_stubs_credentials():
    assert settings.supabase_url == "https://example.supabase.co"
    assert settings.supabase_service_role_key == "test-service-role-key"
