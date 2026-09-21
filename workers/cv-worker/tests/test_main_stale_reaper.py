from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from src import main as worker_main


class _RowsQuery:
    def __init__(self, rows, updates, name):
        self._rows = rows
        self._updates = updates
        self._name = name
        self.payload = None
        self.filters = []

    def select(self, columns="*"):
        return self

    def update(self, payload):
        self.payload = payload
        return self

    def eq(self, column, value):
        self.filters.append((column, value))
        return self

    def execute(self):
        if self.payload is None:
            return SimpleNamespace(data=self._rows)
        self._updates.append((self._name, dict(self.payload), list(self.filters)))
        return SimpleNamespace(data=[])


class _RowsClient:
    def __init__(self, rows, updates):
        self._rows = rows
        self.updates = updates

    def table(self, name):
        return _RowsQuery(self._rows, self.updates, name)


def test_reaper_requeues_stale_processing_job(monkeypatch):
    now = datetime(2026, 9, 21, 18, 0, tzinfo=timezone.utc)
    rows = [
        {
            "id": "stale-1",
            "worker_attempts": 1,
            "worker_locked_at": now - timedelta(hours=5),
            "updated_at": None,
            "started_at": None,
        },
        {
            "id": "fresh-1",
            "worker_attempts": 1,
            "worker_locked_at": now - timedelta(minutes=10),
            "updated_at": None,
            "started_at": None,
        },
    ]
    updates = []
    events = []
    monkeypatch.setattr(worker_main, "client", _RowsClient(rows, updates))
    monkeypatch.setattr(
        worker_main,
        "emit_event",
        lambda request_id, event, payload=None: events.append((request_id, event, payload)),
    )

    reaped = worker_main.reap_stale_processing_jobs(now=now)

    assert reaped == 1
    assert len(updates) == 1
    name, payload, filters = updates[0]
    assert name == "cv_requests"
    assert payload["status"] == "submitted"
    assert payload["worker_locked_at"] is None
    assert filters == [("id", "stale-1")]
    assert events == [
        ("stale-1", "job_requeued_after_stale_lock", {"attempts": 1, "age_minutes": 300.0})
    ]


def test_reaper_fails_stale_job_with_exhausted_attempts(monkeypatch):
    now = datetime(2026, 9, 21, 18, 0, tzinfo=timezone.utc)
    rows = [
        {
            "id": "stale-2",
            "worker_attempts": worker_main.settings.max_attempts,
            "worker_locked_at": now - timedelta(hours=3),
            "updated_at": None,
            "started_at": None,
        }
    ]
    updates = []
    events = []
    monkeypatch.setattr(worker_main, "client", _RowsClient(rows, updates))
    monkeypatch.setattr(
        worker_main,
        "emit_event",
        lambda request_id, event, payload=None: events.append((request_id, event, payload)),
    )

    reaped = worker_main.reap_stale_processing_jobs(now=now)

    assert reaped == 1
    assert updates[0][1]["status"] == "failed"
    assert events[0][1] == "job_failed_after_stale_lock"


def test_reaper_ignores_recent_processing_rows(monkeypatch):
    now = datetime(2026, 9, 21, 18, 0, tzinfo=timezone.utc)
    rows = [
        {
            "id": "active-1",
            "worker_attempts": 1,
            "worker_locked_at": now - timedelta(minutes=5),
            "updated_at": None,
            "started_at": None,
        }
    ]
    updates = []
    monkeypatch.setattr(worker_main, "client", _RowsClient(rows, updates))

    assert worker_main.reap_stale_processing_jobs(now=now) == 0
    assert updates == []


def test_reaper_falls_back_to_updated_at_when_lock_missing(monkeypatch):
    now = datetime(2026, 9, 21, 18, 0, tzinfo=timezone.utc)
    rows = [
        {
            "id": "stale-3",
            "worker_attempts": 1,
            "worker_locked_at": None,
            "updated_at": (now - timedelta(hours=4)).isoformat(),
            "started_at": None,
        }
    ]
    updates = []
    monkeypatch.setattr(worker_main, "client", _RowsClient(rows, updates))
    monkeypatch.setattr(worker_main, "emit_event", lambda *args, **kwargs: None)

    assert worker_main.reap_stale_processing_jobs(now=now) == 1
    assert updates[0][1]["status"] == "submitted"
