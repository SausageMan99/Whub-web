from types import SimpleNamespace

import pytest

from src import main as worker_main


def _job(request_id: str = "cleanup-request") -> dict:
    return {
        "id": request_id,
        "candidate_first_name": "Alice",
        "instructions": "",
    }


def test_process_job_removes_workdir_on_success(tmp_path, monkeypatch):
    monkeypatch.setattr(worker_main.settings, "tmp_dir", str(tmp_path))
    monkeypatch.setattr(worker_main, "emit_event", lambda *args, **kwargs: None)
    monkeypatch.setattr(worker_main, "download_source", lambda job, workdir: workdir / "source.pdf")
    monkeypatch.setattr(worker_main, "extract_pdf_text", lambda source: "Prénom NOM Alice Example")
    monkeypatch.setattr(
        worker_main,
        "sanitize_source_text",
        lambda text, first_name: SimpleNamespace(text=text, report=SimpleNamespace()),
    )

    class _TableQuery:
        data = []

        def select(self, *args, **kwargs):
            return self

        def eq(self, *args, **kwargs):
            return self

        def update(self, *args, **kwargs):
            return self

        def execute(self):
            return self

    class _Client:
        def table(self, *args, **kwargs):
            return _TableQuery()

    monkeypatch.setattr(worker_main, "client", _Client())
    monkeypatch.setattr(worker_main, "build_whub_json", lambda *args, **kwargs: {"name": "Alice"})
    monkeypatch.setattr(worker_main, "enforce_client_first_name", lambda *args, **kwargs: None)
    monkeypatch.setattr(worker_main, "assert_no_contact_in_json", lambda *args, **kwargs: None)
    monkeypatch.setattr(worker_main, "build_layout_packing_options", lambda structured: {})
    monkeypatch.setattr(worker_main, "forbidden_candidate_name_parts", lambda *args, **kwargs: [])
    monkeypatch.setattr(
        worker_main,
        "run_bounded_layout_variant_loop",
        lambda **kwargs: SimpleNamespace(
            hard_failure=None,
            selected=SimpleNamespace(name="default"),
            selected_pdf=b"%PDF-1.4",
            selected_report={},
            attempts=[SimpleNamespace(name="default", status="passed", score=1.0)],
        ),
    )
    monkeypatch.setattr(worker_main, "classify_qa_report", lambda report: ("passed", []))
    monkeypatch.setattr(worker_main, "save_version", lambda *args, **kwargs: {"id": "version-1", "version_number": 1})

    job = _job()
    worker_main.process_job(job)

    assert not (tmp_path / job["id"]).exists()


def test_process_job_removes_workdir_on_exception(tmp_path, monkeypatch):
    monkeypatch.setattr(worker_main.settings, "tmp_dir", str(tmp_path))
    monkeypatch.setattr(worker_main, "emit_event", lambda *args, **kwargs: None)

    def fail_after_workdir_created(job, workdir):
        assert workdir.exists()
        (workdir / "marker.txt").write_text("created")
        raise RuntimeError("boom")

    monkeypatch.setattr(worker_main, "download_source", fail_after_workdir_created)

    job = _job("cleanup-request-failure")
    with pytest.raises(RuntimeError, match="boom"):
        worker_main.process_job(job)

    assert not (tmp_path / job["id"]).exists()
