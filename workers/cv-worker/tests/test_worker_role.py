"""
test_worker_role.py — TDD for Task 1.3

Verifies that the worker no longer uses service_role_key (full admin) and
instead connects via a dedicated PostgreSQL role 'whub_worker' with limited
permissions (SELECT/INSERT/UPDATE on cv_requests, cv_versions, cv_comments,
cv_events; storage.objects operations).

TDD Step 1 (FAIL):  Old implementation uses service_role_key — test documents vulnerability.
TDD Step 4 (PASS):  New implementation uses worker_db_url — test verifies role confinement.
"""

from unittest.mock import ANY, MagicMock, patch

import pytest


# ─────────────────────────────────────────────────────────────────────
# Helpers — set up a mock-backed _WorkerDatabaseClient
# ─────────────────────────────────────────────────────────────────────

def _make_mock_database_client(
    db_url: str = "postgresql://whub_worker:***@localhost:5432/testdb",
    return_rows: list[dict] | None = None,
) -> tuple:
    """
    Create a _WorkerDatabaseClient with a mock psycopg2 connection
    and cursor.  Returns (client, mock_conn, mock_cursor).
    """
    from src.supabase_client import _WorkerDatabaseClient

    client = _WorkerDatabaseClient(db_url, supabase_url="")
    mock_conn = MagicMock(spec=["cursor", "commit", "closed"])
    mock_cursor = MagicMock()
    mock_conn.closed = False
    mock_conn.cursor.return_value.__enter__.return_value = mock_cursor
    if return_rows is not None:
        mock_cursor.fetchall.return_value = [dict(r) for r in return_rows]
    else:
        mock_cursor.fetchall.return_value = []
    client._conn = mock_conn

    return client, mock_conn, mock_cursor


# ─────────────────────────────────────────────────────────────────────
# TDD Step 1 (FAIL) — current vulnerability is now FIXED (test pivots)
# ─────────────────────────────────────────────────────────────────────

def test_worker_no_longer_uses_service_role_key():
    """
    TDD Step 1 → Step 4 pivot.

    The worker no longer uses service_role_key.  The client should
    be a _WorkerDatabaseClient, NOT a supabase.Client.
    """
    from src.supabase_client import client, _WorkerDatabaseClient

    assert isinstance(client, _WorkerDatabaseClient), (
        "SECURITY FIX: worker no longer uses service_role_key; "
        "client is now a _WorkerDatabaseClient backed by dedicated role"
    )


def test_worker_client_does_not_carry_service_role_key():
    """The client should not have a service_role_key attribute."""
    from src.supabase_client import client

    assert not hasattr(client, "_service_role_key"), (
        "Client should not carry service_role_key"
    )


def test_supabase_client_source_has_no_service_role_fallback():
    """The module must not import/create a Supabase client with service_role_key fallback."""
    from pathlib import Path

    source = Path("src/supabase_client.py").read_text()
    assert "_supabase_create_client" not in source
    assert "settings.supabase_service_role_key" not in source
    assert "FALLBACK" not in source


# ─────────────────────────────────────────────────────────────────────
# TDD Step 4 (PASS) — new role-confinement tests
# ─────────────────────────────────────────────────────────────────────

class TestWorkerRoleConfinement:
    """Tests that apply once the worker uses a dedicated role."""

    def test_client_is_worker_database_client(self):
        """After fix, client is a _WorkerDatabaseClient wrapper."""
        from src.supabase_client import client, _WorkerDatabaseClient

        assert isinstance(client, _WorkerDatabaseClient)

    def test_client_passes_worker_db_url_to_connection(self):
        """
        Verify that _WorkerDatabaseClient uses the worker_db_url
        from settings when creating the connection string.
        """
        from src.supabase_client import _WorkerDatabaseClient

        client = _WorkerDatabaseClient("postgresql://whub_worker:***@testhost:6543/postgres?pgbouncer=true")
        assert client.db_url == "postgresql://whub_worker:***@testhost:6543/postgres?pgbouncer=true"

    def test_table_select_execute_returns_data_attribute(self):
        """
        Verify that the wrapper's query-builder API matches the
        shape expected by callers: .table().select().eq().execute()
        returns an object with .data.
        """
        client, mock_conn, mock_cursor = _make_mock_database_client(
            return_rows=[{"id": "abc", "status": "processing"}]
        )

        mock_cursor.fetchall.return_value = [{"id": "abc", "status": "processing"}]
        mock_cursor.description = [("id",), ("status",)]

        result = client.table("cv_requests").select("*").eq("id", "abc").execute()

        assert hasattr(result, "data")
        assert result.data == [{"id": "abc", "status": "processing"}]

        # Verify the SQL was built correctly
        called_sql = mock_cursor.execute.call_args[0][0]
        assert "SELECT" in called_sql
        assert "cv_requests" in called_sql
        assert "id = " in called_sql.lower() or "%s" in called_sql

    def test_rpc_execute_returns_data_attribute(self):
        """Verify .rpc().execute() matches supabase-py's call pattern."""
        client, mock_conn, mock_cursor = _make_mock_database_client(
            return_rows=[{"id": "req-1", "status": "processing"}]
        )

        mock_cursor.fetchall.return_value = [{"id": "req-1", "status": "processing"}]
        mock_cursor.description = [("id",), ("status",)]

        rpc_call = client.rpc("claim_next_cv_request", {"worker_name": "test-worker"})
        assert hasattr(rpc_call, "execute")

        result = rpc_call.execute()

        assert hasattr(result, "data")
        assert len(result.data) == 1
        assert result.data[0]["id"] == "req-1"

        # Verify the SQL calls the function with named args
        called_sql = mock_cursor.execute.call_args[0][0]
        assert "claim_next_cv_request" in called_sql
        assert "worker_name" in called_sql

    def test_table_insert_returns_new_row(self):
        """Verify .table().insert() returns the inserted row in .data."""
        client, mock_conn, mock_cursor = _make_mock_database_client(
            return_rows=[{"id": "new-version-uuid", "version_number": 1}]
        )

        mock_cursor.fetchall.return_value = [{"id": "new-version-uuid", "version_number": 1}]
        mock_cursor.description = [("id",), ("version_number",)]

        result = client.table("cv_versions").insert({
            "request_id": "req-1",
            "version_number": 1,
        }).execute()

        assert hasattr(result, "data")
        assert result.data[0]["id"] == "new-version-uuid"

        # Verify SQL is an INSERT
        called_sql = mock_cursor.execute.call_args[0][0]
        assert "INSERT INTO" in called_sql.upper()
        assert "cv_versions" in called_sql

    def test_table_update_returns_updated_data(self):
        """Verify .table().update() works and returns .data."""
        client, mock_conn, mock_cursor = _make_mock_database_client(
            return_rows=[{"id": "req-1", "status": "ready"}]
        )

        mock_cursor.fetchall.return_value = [{"id": "req-1", "status": "ready"}]
        mock_cursor.description = [("id",), ("status",)]

        result = client.table("cv_requests").update({"status": "ready"}).eq("id", "req-1").execute()

        assert hasattr(result, "data")
        assert result.data[0]["status"] == "ready"

        # Verify SQL is an UPDATE with WHERE
        called_sql = mock_cursor.execute.call_args[0][0]
        assert "UPDATE" in called_sql.upper()
        assert "SET" in called_sql.upper()
        assert "id" in called_sql.lower() or "WHERE" in called_sql.upper()

    def test_storage_upload_works(self):
        """Verify .storage.from_().upload() is callable."""
        client, mock_conn, mock_cursor = _make_mock_database_client()

        mock_storage = MagicMock()
        mock_bucket = MagicMock()
        mock_storage.from_.return_value = mock_bucket
        client._storage = mock_storage

        client.storage.from_("cv-finals").upload(
            "path/to/file.pdf", b"pdf-data", {"content-type": "application/pdf"}
        )

        mock_storage.from_.assert_called_once_with("cv-finals")
        mock_bucket.upload.assert_called_once()

    @patch("src.supabase_client.create_storage_client")
    def test_storage_uses_configured_anon_key_for_rest_client(self, mock_create_storage_client):
        """Storage REST client should use the anon key, never a service-role fallback."""
        from src.supabase_client import _WorkerDatabaseClient

        _WorkerDatabaseClient(
            "postgresql://whub_worker:***@localhost:5432/testdb",
            supabase_url="https://example.supabase.co",
            supabase_anon_key="anon-test-key",
        )

        mock_create_storage_client.assert_called_once_with(
            url="https://example.supabase.co/storage/v1",
            headers={"apikey": "anon-test-key", "Authorization": "Bearer anon-test-key"},
            is_async=False,
        )

    def test_storage_requires_url_and_anon_key(self):
        """Missing anon key should fail early when storage is accessed."""
        from src.supabase_client import _WorkerDatabaseClient

        client = _WorkerDatabaseClient(
            "postgresql://whub_worker:***@localhost:5432/testdb",
            supabase_url="https://example.supabase.co",
            supabase_anon_key="",
        )

        with pytest.raises(RuntimeError, match="supabase_url and supabase_anon_key"):
            _ = client.storage

    def test_table_select_with_order_and_limit(self):
        """Verify .order() and .limit() are translated to SQL."""
        client, mock_conn, mock_cursor = _make_mock_database_client(
            return_rows=[{"id": "v1", "version_number": 3}]
        )

        mock_cursor.fetchall.return_value = [{"id": "v1", "version_number": 3}]
        mock_cursor.description = [("id",), ("version_number",)]

        result = (
            client.table("cv_versions")
            .select("version_number")
            .eq("request_id", "req-1")
            .order("version_number", desc=True)
            .limit(1)
            .execute()
        )

        assert hasattr(result, "data")
        assert result.data[0]["version_number"] == 3

        called_sql = mock_cursor.execute.call_args[0][0]
        assert "ORDER BY" in called_sql.upper()
        assert "DESC" in called_sql.upper()
        assert "LIMIT" in called_sql.upper()

    def test_table_select_returns_empty_data_when_no_rows(self):
        """Verify that SELECT returning no rows yields data=[]."""
        client, mock_conn, mock_cursor = _make_mock_database_client(return_rows=[])

        mock_cursor.fetchall.return_value = []
        mock_cursor.description = []

        result = client.table("cv_comments").select("*").eq("request_id", "nonexistent").execute()

        assert hasattr(result, "data")
        assert result.data == []


# ─────────────────────────────────────────────────────────────────────
# Backward compatibility / transition period
# ─────────────────────────────────────────────────────────────────────

def test_settings_has_worker_db_url():
    """The settings object should have worker_db_url."""
    from src.config import settings

    assert hasattr(settings, "worker_db_url")
    assert hasattr(settings, "supabase_anon_key")
    assert hasattr(settings, "supabase_service_role_key")


def test_required_preflight_settings_use_worker_role_not_service_role():
    """Preflight must require worker role credentials, not service_role_key."""
    from src.preflight import REQUIRED_SUPABASE_SETTINGS

    assert "worker_db_url" in REQUIRED_SUPABASE_SETTINGS
    assert "supabase_anon_key" in REQUIRED_SUPABASE_SETTINGS
    assert "supabase_service_role_key" not in REQUIRED_SUPABASE_SETTINGS


def test_worker_role_migration_grants_only_claim_rpc():
    """Migration should confine whub_worker to the RPC the worker actually calls."""
    from pathlib import Path

    sql = Path("../../supabase/migrations/008_worker_role.sql").resolve().read_text()
    grant_lines = [
        line.strip().lower()
        for line in sql.splitlines()
        if line.strip().lower().startswith("grant execute on function")
    ]

    assert grant_lines == [
        "grant execute on function public.claim_next_cv_request(worker_name text) to whub_worker;"
    ]
    forbidden = (
        "verify_access_code",
        "rotate_access_code",
        "generate_access_code",
        "hash_access_code",
        "is_allowed_user",
        "current_user_role",
    )
    for function_name in forbidden:
        assert not any(function_name in line for line in grant_lines)
