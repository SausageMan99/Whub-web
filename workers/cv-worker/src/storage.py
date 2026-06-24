from pathlib import Path
from datetime import datetime, timezone
import json
import logging
from typing import Any, TypedDict
from .config import settings
from .supabase_client import client

class SavedVersion(TypedDict):
    id: str
    version_number: int


log = logging.getLogger("whub-cv-worker.storage")


def upload_bytes(bucket: str, path: str, data: bytes, content_type: str, *, owner: str | None = None) -> str:
    """Upload bytes to storage. If owner is provided, set metadata.owner for RLS policies."""
    storage_client = client.storage
    options: dict[str, Any] = {"content-type": content_type, "upsert": "true"}
    if owner:
        options["metadata"] = {"owner": owner}
    storage_client.from_(bucket).upload(path, data, options)
    return path


def upload_file(bucket: str, path: str, file_path: Path, content_type: str, *, owner: str | None = None) -> str:
    """Upload file to storage with optional owner metadata."""
    storage_client = client.storage
    options: dict[str, Any] = {"content-type": content_type, "upsert": "true"}
    if owner:
        options["metadata"] = {"owner": owner}
    storage_client.from_(bucket).upload(path, file_path.read_bytes(), options)
    return path


def download_bytes(bucket: str, path: str) -> bytes:
    """Download bytes from storage."""
    return client.storage.from_(bucket).download(path)


def save_version(
    request_id: str,
    structured_json: dict,
    pdf_path: Path,
    qa_report: dict,
    *,
    request_status: str = "ready",
    qa_status: str = "passed",
    owner: str,
) -> SavedVersion:
    if request_status not in {"ready", "draft_ready"}:
        raise ValueError(f"unsupported version request_status: {request_status}")
    if qa_status not in {"passed", "draft"}:
        raise ValueError(f"unsupported version qa_status: {qa_status}")
    if request_status == "ready" and qa_status != "passed":
        raise ValueError("ready requests must have passed QA")
    if request_status == "draft_ready" and qa_status != "draft":
        raise ValueError("draft_ready requests must have draft QA status")

    version = client.table("cv_versions").insert({
        "request_id": request_id,
        "structured_json": structured_json,
        "qa_status": qa_status,
        "qa_report": qa_report,
    }).execute().data[0]
    version_number = int(version["version_number"])

    # Owner for RLS policies: use request's created_by (passed as owner parameter)
    input_path = f"{request_id}/v{version_number}/input.json"
    final_path = f"{request_id}/v{version_number}/cv-whub.pdf"
    qa_path = f"{request_id}/v{version_number}/qa.json"
    # Critical artifacts first: the final PDF and QA report must be stored before
    # the request can be marked ready/draft_ready. The renderer input JSON is a
    # useful debug artifact, but Storage RLS/policy drift must not turn an
    # already rendered + QA-passed CV into a failed request.
    final_path = upload_bytes(settings.cv_finals_bucket, final_path, pdf_path.read_bytes(), "application/pdf", owner=owner)
    qa_path = upload_bytes(settings.cv_artifacts_bucket, qa_path, json.dumps(qa_report, ensure_ascii=False, indent=2).encode(), "application/json", owner=owner)
    renderer_input_path: str | None
    try:
        renderer_input_path = upload_bytes(
            settings.cv_renderer_inputs_bucket,
            input_path,
            json.dumps(structured_json, ensure_ascii=False, indent=2).encode(),
            "application/json",
            owner=owner,
        )
    except Exception as exc:
        renderer_input_path = None
        log.warning(
            "non-critical renderer input upload failed request_id=%s version=%s bucket=%s path=%s error=%s",
            request_id,
            version_number,
            settings.cv_renderer_inputs_bucket,
            input_path,
            exc,
        )
    client.table("cv_versions").update({
        "renderer_input_path": renderer_input_path,
        "final_pdf_path": final_path,
    }).eq("id", version["id"]).execute()
    now = datetime.now(timezone.utc).isoformat()
    client.table("cv_requests").update({
        "status": request_status,
        "current_version_id": version["id"],
        "last_error": None,
        "ready_at": now,
        "updated_at": now,
    }).eq("id", request_id).execute()
    return {"id": version["id"], "version_number": version_number}


def save_success(request_id: str, structured_json: dict, pdf_path: Path, qa_report: dict, owner: str) -> str:
    return save_version(request_id, structured_json, pdf_path, qa_report, request_status="ready", qa_status="passed", owner=owner)["id"]