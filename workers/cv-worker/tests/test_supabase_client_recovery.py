"""Recovery: a failed statement must not poison the shared connection.

Incident 2026-09-21 (worker log 18:12:36 UTC): a NUL byte in a draft JSON
made the version INSERT fail with ``UntranslatableCharacter``; with no
rollback, the connection stayed in an aborted transaction and the failure
path itself (status update, event insert) raised ``InFailedSqlTransaction``
— the process then died and systemd restarted the worker. The executors
must roll back (or drop) the connection so it is usable again afterwards.
"""

import pytest

from src import supabase_client as sc


class _FakeCursor:
    def __init__(self, error):
        self._error = error
        self.executed = []

    def __enter__(self):
        return self

    def __exit__(self, *exc_info):
        return False

    def execute(self, sql, params=None):
        if self._error is not None:
            raise self._error
        self.executed.append((sql, params))

    def fetchall(self):
        return []


class _FakeConn:
    def __init__(self, error=None):
        self.error = error
        self.rollbacks = 0
        self.commits = 0
        self.closed = False

    def cursor(self, cursor_factory=None):
        return _FakeCursor(self.error)

    def commit(self):
        self.commits += 1

    def rollback(self):
        self.rollbacks += 1

    def close(self):
        self.closed = True


def _client_with(conn):
    client = sc._WorkerDatabaseClient(db_url="postgresql://u:p@localhost:5432/x")
    client._conn = conn  # inject; the lazy conn property will return it
    return client


def test_query_builder_rolls_back_and_connection_stays_usable():
    conn = _FakeConn(error=Exception("unsupported Unicode escape sequence"))
    client = _client_with(conn)

    with pytest.raises(Exception, match="Unicode"):
        client.table("cv_versions").insert({"draft": "x"}).execute()

    assert conn.rollbacks == 1
    assert not conn.closed

    # The same connection must serve the next query once the error is gone.
    conn.error = None
    result = client.table("cv_versions").select("id").execute()
    assert result.data == []


def test_rpc_call_rolls_back_on_error():
    conn = _FakeConn(error=Exception("boom"))
    client = _client_with(conn)

    with pytest.raises(Exception, match="boom"):
        client.rpc("claim_next_cv_request", {"claim_worker": "w"}).execute()

    assert conn.rollbacks == 1
