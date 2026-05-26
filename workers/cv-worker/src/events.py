from .supabase_client import client

def emit_event(request_id: str, event_type: str, payload: dict | None = None, actor_type: str = "worker") -> None:
    client.table("cv_events").insert({
        "request_id": request_id,
        "actor_type": actor_type,
        "event_type": event_type,
        "payload": payload or {},
    }).execute()
