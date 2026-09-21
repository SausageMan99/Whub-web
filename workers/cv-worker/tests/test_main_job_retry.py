from types import SimpleNamespace

import pytest

from src import main as worker_main
from src.structuring import StructuringError


class _FakeQuery:
    def __init__(self, updates):
        self._updates = updates
        self.payload = None
        self.filters = []

    def update(self, payload):
        self.payload = payload
        return self

    def eq(self, column, value):
        self.filters.append((column, value))
        return self

    def execute(self):
        self._updates.append((dict(self.payload or {}), list(self.filters)))
        return SimpleNamespace(data=[])


class _FakeClient:
    def __init__(self, updates):
        self.updates = updates

    def table(self, name):
        return _FakeQuery(self.updates)


def test_retryable_failure_requeues_job_before_max_attempts(monkeypatch):
    updates = []
    events = []
    fail_calls = []
    monkeypatch.setattr(worker_main, "client", _FakeClient(updates))
    monkeypatch.setattr(
        worker_main,
        "emit_event",
        lambda request_id, event, payload=None: events.append((request_id, event, payload)),
    )
    monkeypatch.setattr(worker_main, "fail_job", lambda *args: fail_calls.append(args))

    worker_main.handle_job_failure(
        {"id": "req-1", "worker_attempts": 1},
        StructuringError("Timeout structuration Hermes après 600.00s"),
    )

    assert not fail_calls
    assert len(updates) == 1
    payload, filters = updates[0]
    assert payload["status"] == "submitted"
    assert payload["worker_locked_at"] is None
    assert payload["worker_locked_by"] is None
    assert f"tentative 1/{worker_main.settings.max_attempts}" in payload["last_error"]
    assert filters == [("id", "req-1")]
    assert events == [(
        "req-1",
        "job_retry_scheduled",
        {
            "category": "model_timeout",
            "attempt": 1,
            "max_attempts": worker_main.settings.max_attempts,
        },
    )]


def test_retryable_failure_fails_for_real_when_budget_exhausted(monkeypatch):
    updates = []
    fail_calls = []
    monkeypatch.setattr(worker_main, "client", _FakeClient(updates))
    monkeypatch.setattr(worker_main, "emit_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(worker_main, "fail_job", lambda *args: fail_calls.append(args))

    worker_main.handle_job_failure(
        {"id": "req-2", "worker_attempts": worker_main.settings.max_attempts},
        StructuringError("Timeout structuration Hermes après 600.00s"),
    )

    assert not updates
    assert fail_calls
    assert fail_calls[0][0]["id"] == "req-2"
    assert fail_calls[0][2] == "failed"


def test_deterministic_failure_never_retries(monkeypatch):
    updates = []
    fail_calls = []
    monkeypatch.setattr(worker_main, "client", _FakeClient(updates))
    monkeypatch.setattr(worker_main, "emit_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(worker_main, "fail_job", lambda *args: fail_calls.append(args))

    worker_main.handle_job_failure(
        {"id": "req-3", "worker_attempts": 1},
        "Fidélité source insuffisante: source_coverage_missing_experience_item",
    )

    assert not updates
    assert fail_calls
    assert fail_calls[0][2] == "failed"


def test_pre_model_failure_is_not_retried(monkeypatch):
    updates = []
    fail_calls = []
    monkeypatch.setattr(worker_main, "client", _FakeClient(updates))
    monkeypatch.setattr(worker_main, "emit_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(worker_main, "fail_job", lambda *args: fail_calls.append(args))

    worker_main.handle_job_failure(
        {"id": "req-4", "worker_attempts": 1},
        ValueError("embedded null byte"),
    )

    assert not updates
    assert fail_calls
    assert fail_calls[0][2] == "failed"


def test_requeue_db_error_falls_back_to_fail(monkeypatch):
    class _BoomQuery(_FakeQuery):
        def execute(self):
            raise RuntimeError("db down")

    class _BoomClient:
        def table(self, name):
            return _BoomQuery([])

    fail_calls = []
    monkeypatch.setattr(worker_main, "client", _BoomClient())
    monkeypatch.setattr(worker_main, "emit_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(worker_main, "fail_job", lambda *args: fail_calls.append(args))

    worker_main.handle_job_failure(
        {"id": "req-5", "worker_attempts": 1},
        StructuringError("Timeout structuration Hermes après 600.00s"),
    )

    assert fail_calls
    assert fail_calls[0][0]["id"] == "req-5"
