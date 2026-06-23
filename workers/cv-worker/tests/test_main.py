import pytest

from src import main as worker_main


class StopPolling(Exception):
    pass


def test_poll_with_backoff_uses_exponential_delays_for_consecutive_poll_errors():
    delays = []

    def failing_claim():
        raise RuntimeError("database unavailable")

    def recording_sleep(delay):
        delays.append(delay)
        if len(delays) == 5:
            raise StopPolling

    with pytest.raises(StopPolling):
        worker_main.poll_with_backoff(
            claim_func=failing_claim,
            process_func=lambda job: None,
            sleep_func=recording_sleep,
            base_delay=10,
        )

    assert delays == [10, 20, 40, 80, 160]


def test_poll_with_backoff_caps_exponential_backoff_at_300_seconds():
    delays = []

    def failing_claim():
        raise RuntimeError("database unavailable")

    def recording_sleep(delay):
        delays.append(delay)
        if len(delays) == 7:
            raise StopPolling

    with pytest.raises(StopPolling):
        worker_main.poll_with_backoff(
            claim_func=failing_claim,
            process_func=lambda job: None,
            sleep_func=recording_sleep,
            base_delay=10,
        )

    assert delays == [10, 20, 40, 80, 160, 300, 300]


def test_circuit_breaker_opens_after_10_consecutive_errors():
    now = [1_000.0]
    breaker = worker_main.CircuitBreaker(
        failure_threshold=10,
        recovery_timeout=300,
        time_func=lambda: now[0],
    )

    for _ in range(9):
        assert breaker.allow_request()
        breaker.record_failure()
        assert breaker.state == "closed"

    assert breaker.allow_request()
    breaker.record_failure()

    assert breaker.state == "open"
    assert not breaker.allow_request()


def test_circuit_breaker_transitions_to_half_open_after_recovery_timeout():
    now = [1_000.0]
    breaker = worker_main.CircuitBreaker(
        failure_threshold=2,
        recovery_timeout=300,
        time_func=lambda: now[0],
    )

    breaker.record_failure()
    breaker.record_failure()
    assert breaker.state == "open"

    now[0] += 299
    assert not breaker.allow_request()
    assert breaker.state == "open"

    now[0] += 1
    assert breaker.allow_request()
    assert breaker.state == "half-open"

    breaker.record_success()
    assert breaker.state == "closed"
    assert breaker.failure_count == 0


class TestProcessJobTelegramStyleRevisions:
    """Lock the Telegram-equivalent portal flow inside ``process_job``.

    The portal produces ``cv_requests`` rows with ``instructions`` (initial
    free message) plus ``cv_comments`` revisions (V2/V3 corrections). The
    worker must load the unresolved revisions, prepend any history summary,
    and pass both ``instructions`` and ``comments`` to ``build_whub_json``
    so the structuring prompt reflects the conversation.
    """

    def test_process_job_passes_unresolved_web_revisions_to_structuring(
        self, monkeypatch, tmp_path
    ):
        captured: dict = {}
        pdf_path = tmp_path / "source.pdf"
        pdf_path.write_bytes(b"%PDF source")

        source_text = "\n".join(
            [
                "Alice",
                "Compétences: Python, Kubernetes, Terraform, architecture cloud.",
                "Expériences: pilotage de projets data et industrialisation de plateformes internes.",
                "Réalisations: migration applicative, automatisation CI/CD, sécurisation des déploiements.",
                "Formation: école d'ingénieur, certifications cloud, ateliers agiles et mentorat technique.",
                "Langues: français, anglais professionnel, communication avec équipes produit et métier.",
            ]
        )

        monkeypatch.setattr(worker_main.settings, "tmp_dir", str(tmp_path))
        monkeypatch.setattr(worker_main, "download_source", lambda job, workdir: pdf_path)
        monkeypatch.setattr(worker_main, "extract_pdf_text", lambda source: source_text)

        class _FakeReport:
            raw_chars = len(source_text)
            sanitized_chars = len(source_text)
            removed_email_count = 0
            removed_phone_count = 0
            removed_url_count = 0
            removed_linkedin_count = 0
            removed_github_profile_count = 0
            removed_address_line_count = 0
            removed_contact_label_line_count = 0
            removed_hellowork_line_count = 0
            removed_empty_or_boilerplate_line_count = 0
            warnings = []

        class _FakeSanitization:
            text = source_text
            report = _FakeReport()

        monkeypatch.setattr(
            worker_main,
            "sanitize_source_text",
            lambda text, first_name: _FakeSanitization(),
        )

        monkeypatch.setattr(
            worker_main,
            "build_whub_json",
            lambda text, instructions, comments, candidate_first_name: (
                captured.update(
                    {
                        "text": text,
                        "instructions": instructions,
                        "comments": comments,
                        "candidate_first_name": candidate_first_name,
                    }
                ),
                {
                    "name": "ALICE",
                    "title": "Développeuse Python",
                    "formations": [],
                    "skills": [{"category": "Tech", "items": ["Python"]}],
                    "experiences": [],
                },
            )[1],
        )
        monkeypatch.setattr(worker_main, "assert_no_contact_in_json", lambda structured: None)
        monkeypatch.setattr(worker_main, "enforce_client_first_name", lambda structured, first_name: None)
        monkeypatch.setattr(worker_main, "render_pdf", lambda *args, **kwargs: pdf_path)

        def _fake_run_qa(*args, **kwargs):
            return {
                "passed": True,
                "pages": 1,
                "contact_hits": [],
                "bad_glyphs": False,
                "content_integrity_issues": [],
                "text_overflow_hits": [],
                "layout_issues": [],
                "has_logo": True,
                "has_watermark": True,
            }

        monkeypatch.setattr(worker_main, "run_qa", _fake_run_qa)
        monkeypatch.setattr(
            worker_main,
            "save_version",
            lambda *args, **kwargs: {"id": "v1", "version_number": 1},
        )
        monkeypatch.setattr(worker_main, "emit_event", lambda *args, **kwargs: None)

        class _Table:
            def __init__(self, table: str):
                self.table = table

            def select(self, *_args):
                return self

            def update(self, *_args, **_kwargs):
                return self

            def eq(self, *_args):
                return self

            def execute(self):
                if self.table == "cv_comments":
                    return type(
                        "Res",
                        (),
                        {
                            "data": [
                                {
                                    "body": "V2: change juste le titre en Tech Lead Python.",
                                    "comment_type": "revision",
                                }
                            ]
                        },
                    )()
                if self.table == "cv_versions":
                    return type("Res", (), {"data": []})()
                return type("Res", (), {"data": []})()

        monkeypatch.setattr(worker_main.client, "table", lambda table: _Table(table))

        worker_main.process_job(
            {
                "id": "req1",
                "candidate_first_name": "Alice",
                "instructions": "Mets en avant Python si présent dans le CV.",
                "source_file_path": "req1/source/cv.pdf",
            }
        )

        assert captured["instructions"] == "Mets en avant Python si présent dans le CV."
        assert captured["candidate_first_name"] == "Alice"
        assert any(
            comment.get("body") == "V2: change juste le titre en Tech Lead Python."
            and comment.get("comment_type") == "revision"
            for comment in captured["comments"]
        ), (
            "expected the unresolved web revision to reach build_whub_json; "
            f"got comments={captured.get('comments')!r}"
        )

    def test_process_job_without_unresolved_revisions_passes_empty_comment_list(
        self, monkeypatch, tmp_path
    ):
        """A first submission (no V2/V3 yet) must still thread through cleanly."""

        captured: dict = {}
        pdf_path = tmp_path / "source.pdf"
        pdf_path.write_bytes(b"%PDF source")

        source_text = "\n".join(
            [
                "Alice",
                "Compétences: Python, Kubernetes, Terraform, architecture cloud.",
                "Expériences: pilotage de projets data et industrialisation de plateformes internes.",
                "Réalisations: migration applicative, automatisation CI/CD, sécurisation des déploiements.",
                "Formation: école d'ingénieur, certifications cloud, ateliers agiles et mentorat technique.",
                "Langues: français, anglais professionnel, communication avec équipes produit et métier.",
            ]
        )

        monkeypatch.setattr(worker_main.settings, "tmp_dir", str(tmp_path))
        monkeypatch.setattr(worker_main, "download_source", lambda job, workdir: pdf_path)
        monkeypatch.setattr(worker_main, "extract_pdf_text", lambda source: source_text)

        class _FakeReport:
            raw_chars = len(source_text)
            sanitized_chars = len(source_text)
            removed_email_count = 0
            removed_phone_count = 0
            removed_url_count = 0
            removed_linkedin_count = 0
            removed_github_profile_count = 0
            removed_address_line_count = 0
            removed_contact_label_line_count = 0
            removed_hellowork_line_count = 0
            removed_empty_or_boilerplate_line_count = 0
            warnings = []

        class _FakeSanitization:
            text = source_text
            report = _FakeReport()

        monkeypatch.setattr(
            worker_main,
            "sanitize_source_text",
            lambda text, first_name: _FakeSanitization(),
        )
        monkeypatch.setattr(
            worker_main,
            "build_whub_json",
            lambda text, instructions, comments, candidate_first_name: (
                captured.update(
                    {
                        "instructions": instructions,
                        "comments": list(comments),
                        "candidate_first_name": candidate_first_name,
                    }
                ),
                {
                    "name": "ALICE",
                    "title": "Développeuse Python",
                    "formations": [],
                    "skills": [],
                    "experiences": [],
                },
            )[1],
        )
        monkeypatch.setattr(worker_main, "assert_no_contact_in_json", lambda structured: None)
        monkeypatch.setattr(worker_main, "enforce_client_first_name", lambda structured, first_name: None)
        monkeypatch.setattr(worker_main, "render_pdf", lambda *args, **kwargs: pdf_path)

        def _fake_run_qa(*args, **kwargs):
            return {
                "passed": True,
                "pages": 1,
                "contact_hits": [],
                "bad_glyphs": False,
                "content_integrity_issues": [],
                "text_overflow_hits": [],
                "layout_issues": [],
                "has_logo": True,
                "has_watermark": True,
            }

        monkeypatch.setattr(worker_main, "run_qa", _fake_run_qa)
        monkeypatch.setattr(
            worker_main,
            "save_version",
            lambda *args, **kwargs: {"id": "v1", "version_number": 1},
        )
        monkeypatch.setattr(worker_main, "emit_event", lambda *args, **kwargs: None)

        class _Table:
            def __init__(self, table: str):
                self.table = table

            def select(self, *_args):
                return self

            def update(self, *_args, **_kwargs):
                return self

            def eq(self, *_args):
                return self

            def execute(self):
                return type("Res", (), {"data": []})()

        monkeypatch.setattr(worker_main.client, "table", lambda table: _Table(table))

        worker_main.process_job(
            {
                "id": "req2",
                "candidate_first_name": "Alice",
                "instructions": "",
                "source_file_path": "req2/source/cv.pdf",
            }
        )

        assert captured["instructions"] == ""
        assert captured["candidate_first_name"] == "Alice"
        assert captured["comments"] == []
