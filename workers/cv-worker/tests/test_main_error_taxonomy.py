from types import SimpleNamespace

from src import main as worker_main
from src.source_sanitizer import SourceSanitizationError
from src.structuring import classify_structuring_error, StructuringError


class _FakeQuery:
    def __init__(self):
        self.payload = None
        self.filters = []

    def select(self, columns=""):
        return self

    def update(self, payload):
        self.payload = payload
        return self

    def eq(self, column, value):
        self.filters.append((column, value))
        return self

    def execute(self):
        return SimpleNamespace(data=[])


class _FakeClient:
    def __init__(self):
        self.query = _FakeQuery()

    def table(self, name):
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


class TestSourceSanitizationErrorTaxonomy:
    def test_classifies_source_sanitization_error_with_safe_message(self):
        classified = classify_structuring_error(
            SourceSanitizationError("Texte source trop court après sanitization")
        )

        assert classified == {
            "category": "source_sanitization",
            "message": "Nettoyage de la source CV impossible sans risque de perte de contenu.",
        }

    def test_source_sanitization_public_message_does_not_leak_raw_payload(self):
        raw_email = "jean.dupont@example.com"
        raw_phone = "+33 6 12 34 56 78"
        raw_url = "https://portfolio.example/raw-cv"
        classified = classify_structuring_error(
            SourceSanitizationError(
                f"Texte source trop court après sanitization raw={raw_email} {raw_phone} {raw_url}"
            )
        )

        public_message = classified["message"]
        assert classified["category"] == "source_sanitization"
        assert raw_email not in public_message
        assert raw_phone not in public_message
        assert raw_url not in public_message
        assert "raw" not in public_message.lower()

    def test_safe_sanitization_event_payload_uses_expected_count_fields_only(self):
        report = SimpleNamespace(
            raw_chars=1234,
            sanitized_chars=987,
            removed_email_count=1,
            removed_phone_count=2,
            removed_url_count=3,
            removed_linkedin_count=4,
            removed_github_profile_count=5,
            removed_address_line_count=6,
            removed_contact_label_line_count=7,
            removed_hellowork_line_count=8,
            removed_empty_or_boilerplate_line_count=9,
            warnings=("sanitized_text_shrunk_unusually",),
            raw_ch="jean.dupont@example.com +33 6 12 34 56 78 https://portfolio.example",
        )

        payload = worker_main._build_safe_sanitization_event_payload(report)

        assert set(payload) == {
            "raw_chars",
            "sanitized_chars",
            "removed_email_count",
            "removed_phone_count",
            "removed_url_count",
            "removed_linkedin_count",
            "removed_github_profile_count",
            "removed_address_line_count",
            "removed_contact_label_line_count",
            "removed_hellowork_line_count",
            "removed_empty_or_boilerplate_line_count",
            "warnings",
        }
        assert payload["removed_email_count"] == 1
        assert payload["removed_phone_count"] == 2
        assert payload["warnings"] == ["sanitized_text_shrunk_unusually"]
        payload_repr = repr(payload)
        assert "jean.dupont@example.com" not in payload_repr
        assert "+33 6 12 34 56 78" not in payload_repr
        assert "https://portfolio.example" not in payload_repr

    def test_process_job_source_sanitization_failure_calls_fail_job_with_safe_public_message(self, monkeypatch, tmp_path):
        pdf_path = tmp_path / "source.pdf"
        pdf_path.write_bytes(b"%PDF short source")
        failures = []
        events = []

        def _fail_job(job, error, status="failed"):
            classified = classify_structuring_error(error)
            failures.append((job["id"], status, classified["category"], classified["message"]))

        monkeypatch.setattr(worker_main.settings, "tmp_dir", str(tmp_path))
        monkeypatch.setattr(worker_main, "download_source", lambda job, workdir: pdf_path)
        monkeypatch.setattr(
            worker_main,
            "extract_pdf_text",
            lambda source: "Jean Dupont jean.dupont@example.com +33 6 12 34 56 78",
        )
        monkeypatch.setattr(worker_main, "fail_job", _fail_job)
        monkeypatch.setattr(
            worker_main,
            "emit_event",
            lambda request_id, event, payload=None: events.append((event, payload or {})),
        )

        worker_main.process_job({"id": "req-source-sanitization", "candidate_first_name": "Jean", "instructions": ""})

        assert failures == [
            (
                "req-source-sanitization",
                "failed",
                "source_sanitization",
                "Nettoyage de la source CV impossible sans risque de perte de contenu.",
            )
        ]
        assert [event for event, _payload in events] == ["worker_claimed", "extraction_done"]
        failure_repr = repr(failures)
        assert "jean.dupont@example.com" not in failure_repr
        assert "+33 6 12 34 56 78" not in failure_repr


class TestMissingCandidateFirstNameErrorTaxonomy:
    def test_classifies_missing_candidate_first_name_error_with_safe_message(self):
        classified = classify_structuring_error(
            StructuringError("Prénom candidat manquant et non inférable depuis la source")
        )

        assert classified["category"] == "missing_candidate_first_name"
        assert classified["message"] == "Prénom candidat absent et non inférable depuis le CV source."

    def test_missing_candidate_first_name_public_message_does_not_leak_raw_payload(self):
        raw_payload = "some_secret_raw_value_12345"
        classified = classify_structuring_error(
            StructuringError(f"missing_candidate_first_name: inference failed raw_payload={raw_payload}")
        )

        public_message = classified["message"]
        assert classified["category"] == "missing_candidate_first_name"
        assert raw_payload not in public_message

    def test_missing_candidate_first_name_message_is_in_public_messages_dict(self):
        from src.structuring import STRUCTURING_ERROR_PUBLIC_MESSAGES

        classified = classify_structuring_error(
            StructuringError("missing_candidate_first_name: cannot infer from anonymized source")
        )

        assert classified["message"] == STRUCTURING_ERROR_PUBLIC_MESSAGES["missing_candidate_first_name"]

    def test_process_job_missing_first_name_calls_fail_job_with_safe_public_message(self, monkeypatch, tmp_path):
        pdf_path = tmp_path / "source.pdf"
        pdf_path.write_bytes(b"%PDF fake")
        failures: list[tuple] = []
        events: list[tuple] = []
        build_whub_json_called = []
        fake_client = _FakeClient()

        def _fail_job(job, error, status="failed"):
            classified = classify_structuring_error(error)
            failures.append((job["id"], status, classified["category"], classified["message"]))

        def _track_build_whub_json(*args, **kwargs):
            build_whub_json_called.append(True)
            return {"name": "Ingénieur DevOps"}

        monkeypatch.setattr(worker_main, "client", fake_client)
        monkeypatch.setattr(worker_main.settings, "tmp_dir", str(tmp_path))
        monkeypatch.setattr(worker_main, "download_source", lambda job, workdir: pdf_path)
        # Anonymized CV source: at least 400 chars, no identity line in first 50 lines.
        # Each line has mixed case (uppercase-after-lowercase tokens), so
        # _looks_like_standalone_identity_line returns False for every line.
        monkeypatch.setattr(
            worker_main,
            "extract_pdf_text",
            lambda source: (
                "Expérience professionnelle dans le domaine du développement logiciel senior avec plus de huit ans d'expérience\n"
                "Compétences techniques incluant python java javascript typescript react angular vue node express django flask\n"
                "Projets récents développement d'une plateforme e-commerce avec react et node migration d'une infrastructure\n"
                "Formation master en informatique université paris-saclay licence en mathématiques et informatique\n"
                "Langues français natif anglais courant allemand débutant\n"
                "Centres d'intérêt vélo randonnée photographie lecture voyages cuisine\n"
                "Certifications aws certified solutions architect google cloud professional data engineer\n"
                "Publications contribution à des articles sur le développement web et l'architecture logicielle\n"
                "Recommandations disponibles sur demande\n"
                "Disponibilité immédiate mobilité internationale\n"
            ),
        )
        monkeypatch.setattr(worker_main, "fail_job", _fail_job)
        monkeypatch.setattr(
            worker_main,
            "emit_event",
            lambda request_id, event, payload=None: events.append((event, payload or {})),
        )
        monkeypatch.setattr(worker_main, "build_whub_json", _track_build_whub_json)

        worker_main.process_job({"id": "req-missing-first-name", "candidate_first_name": "", "instructions": ""})

        assert failures == [
            (
                "req-missing-first-name",
                "failed",
                "missing_candidate_first_name",
                "Prénom candidat absent et non inférable depuis le CV source.",
            )
        ]
        assert [event for event, _payload in events] == ["worker_claimed", "extraction_done", "source_sanitized"]
        assert not build_whub_json_called, "build_whub_json should NOT be called when first name cannot be inferred"
        failure_repr = repr(failures)
        assert "Expérience professionnelle" not in failure_repr
