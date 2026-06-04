from pathlib import Path
from datetime import datetime, timezone
import json
from typing import TypedDict
from .config import settings
from .supabase_client import client


class SavedVersion(TypedDict):
    id: str
    version_number: int

def upload_bytes(bucket: str, path: str, data: bytes, content_type: str) -> str:
    client.storage.from_(bucket).upload(path, data, {"content-type": content_type, "upsert": "true"})
    return path

def save_version(
    request_id: str,
    structured_json: dict,
    pdf_path: Path,
    qa_report: dict,
    *,
    request_status: str = "ready",
    qa_status: str = "passed",
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

    input_path = f"{request_id}/v{version_number}/input.json"
    final_path = f"{request_id}/v{version_number}/cv-whub.pdf"
    qa_path = f"{request_id}/v{version_number}/qa.json"
    upload_bytes(settings.cv_renderer_inputs_bucket, input_path, json.dumps(structured_json, ensure_ascii=False, indent=2).encode(), "application/json")
    upload_bytes(settings.cv_finals_bucket, final_path, pdf_path.read_bytes(), "application/pdf")
    upload_bytes(settings.cv_artifacts_bucket, qa_path, json.dumps(qa_report, ensure_ascii=False, indent=2).encode(), "application/json")
    client.table("cv_versions").update({
        "renderer_input_path": input_path,
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


def save_success(request_id: str, structured_json: dict, pdf_path: Path, qa_report: dict) -> str:
    return save_version(request_id, structured_json, pdf_path, qa_report, request_status="ready", qa_status="passed")["id"]
