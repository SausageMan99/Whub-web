from src import main as worker_main


class _FakeQuery:
    def __init__(self):
        self.payload = None
        self.filters = []

    def update(self, payload):
        self.payload = payload
        return self

    def eq(self, column, value):
        self.filters.append((column, value))
        return self

    def execute(self):
        return self


class _FakeClient:
    def __init__(self):
        self.query = _FakeQuery()

    def table(self, name):
        assert name == "cv_requests"
        return self.query


def test_fail_job_persists_safe_taxonomy_message_without_raw_candidate_data(monkeypatch):
    fake_client = _FakeClient()
    events = []
    monkeypatch.setattr(worker_main, "client", fake_client)
    monkeypatch.setattr(worker_main, "emit_event", lambda request_id, status, payload=None: events.append((request_id, status, payload)))

    worker_main.fail_job(
        {"id": "req-1"},
        "Structuration échouée: jean.dupont@example.com +33 6 12 34 56 78 linkedin.com/in/jean-dupont",
        "failed",
    )

    assert fake_client.query.payload is not None
    persisted = fake_client.query.payload["last_error"]
    event_payload = events[0][2]

    assert persisted == "Coordonnées détectées dans la structuration du CV."
    assert event_payload == {"error": persisted, "error_category": "contact_leak"}
    assert "jean.dupont@example.com" not in persisted
    assert "+33" not in persisted
    assert "linkedin.com" not in persisted
