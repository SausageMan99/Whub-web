import json
import subprocess

import httpx
import pytest

from src import llm_backend, structuring
from src.llm_backend import CV_JSON_SCHEMA, build_request_payload, openrouter_runner
from src.structuring import RETRYABLE_STRUCTURING_CATEGORIES, classify_structuring_error


@pytest.fixture(autouse=True)
def _openrouter_settings(monkeypatch):
    monkeypatch.setattr(llm_backend.settings, "openrouter_api_key", "sk-test")
    monkeypatch.setattr(llm_backend.settings, "whub_primary_model", "google/gemini-2.5-flash")
    monkeypatch.setattr(llm_backend.settings, "whub_fallback_model", "")
    monkeypatch.setattr(llm_backend.settings, "whub_llm_reasoning_effort", "")
    monkeypatch.setattr(llm_backend.time, "sleep", lambda _s: None)


def _completion(content, finish_reason="stop"):
    return {
        "model": "google/gemini-2.5-flash",
        "provider": "Google AI Studio",
        "choices": [{"finish_reason": finish_reason, "message": {"content": content}}],
        "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.0001},
    }


def _client(*responses):
    calls = []
    queue = list(responses)

    def handler(request):
        calls.append(json.loads(request.content))
        item = queue.pop(0)
        if isinstance(item, Exception):
            raise item
        status, body = item
        return httpx.Response(status, json=body)

    return httpx.Client(transport=httpx.MockTransport(handler)), calls


VALID_CV = {
    "name": "JEAN",
    "title": "Développeur Java",
    "description": "",
    "formations": [],
    "certifications": [],
    "languages": [{"name": "Anglais", "level": ""}, {"name": "Français", "level": "natif"}],
    "skills": [{"category": "Langages", "items": ["Java"]}],
    "experiences": [],
}


def test_payload_enforces_strict_schema_and_data_policy():
    payload = build_request_payload("prompt")

    assert payload["response_format"]["json_schema"]["strict"] is True
    assert payload["response_format"]["json_schema"]["schema"] is CV_JSON_SCHEMA
    assert payload["provider"] == {"require_parameters": True, "data_collection": "deny"}
    assert payload["messages"][-1] == {"role": "user", "content": "prompt"}
    assert "models" not in payload


def test_payload_lists_fallback_model_when_configured(monkeypatch):
    monkeypatch.setattr(llm_backend.settings, "whub_fallback_model", "anthropic/claude-haiku-5.5")

    payload = build_request_payload("prompt")

    assert payload["models"] == ["google/gemini-2.5-flash", "anthropic/claude-haiku-5.5"]


def test_schema_requires_every_property_for_strict_mode():
    def walk(node):
        if node.get("type") == "object":
            assert set(node["required"]) == set(node["properties"])
            assert node["additionalProperties"] is False
            for child in node["properties"].values():
                walk(child)
        elif node.get("type") == "array":
            walk(node["items"])

    walk(CV_JSON_SCHEMA)


def test_runner_returns_normalized_json_and_drops_empty_optional_fields():
    client, _calls = _client((200, _completion(json.dumps(VALID_CV))))

    returncode, stdout, stderr = openrouter_runner("prompt", 30, client=client)

    data = json.loads(stdout)
    assert (returncode, stderr) == (0, "")
    assert "description" not in data
    assert data["languages"] == [{"name": "Anglais"}, {"name": "Français", "level": "natif"}]


def test_runner_output_is_accepted_by_extract_json():
    client, _calls = _client((200, _completion(json.dumps(VALID_CV))))

    _rc, stdout, _err = openrouter_runner("prompt", 30, client=client)

    assert structuring._extract_json(stdout)["name"] == "JEAN"


def test_runner_reports_truncation_as_failure():
    client, _calls = _client((200, _completion('{"name": "JE', finish_reason="length")))

    returncode, _stdout, stderr = openrouter_runner("prompt", 30, client=client)

    assert returncode == 1
    assert "finish_reason=length" in stderr


def test_runner_retries_once_on_transient_http_status():
    client, calls = _client((503, {"error": {"message": "overloaded"}}), (200, _completion(json.dumps(VALID_CV))))

    returncode, _stdout, _stderr = openrouter_runner("prompt", 30, client=client)

    assert returncode == 0
    assert len(calls) == 2


def test_runner_maps_auth_errors_to_non_retryable_config_error():
    client, calls = _client((401, {"error": {"message": "User not found."}}))

    returncode, _stdout, stderr = openrouter_runner("prompt", 30, client=client)
    category = classify_structuring_error(
        structuring.StructuringError(f"Échec structuration Hermes (single-pass, returncode={returncode}): {stderr}")
    )["category"]

    assert len(calls) == 1
    assert category == "model_config_error"
    assert category not in RETRYABLE_STRUCTURING_CATEGORIES


def test_runner_without_api_key_is_a_config_error(monkeypatch):
    monkeypatch.setattr(llm_backend.settings, "openrouter_api_key", "")

    returncode, _stdout, stderr = openrouter_runner("prompt", 30)

    assert returncode == 1
    assert classify_structuring_error(stderr)["category"] == "model_config_error"


def test_runner_maps_http_timeout_to_subprocess_timeout():
    client, _calls = _client(httpx.ReadTimeout("slow"))

    with pytest.raises(subprocess.TimeoutExpired):
        openrouter_runner("prompt", 30, client=client)


def test_default_runner_follows_backend_setting(monkeypatch):
    monkeypatch.setattr(structuring.settings, "whub_llm_backend", "openrouter")
    assert structuring.default_structuring_runner() is openrouter_runner

    monkeypatch.setattr(structuring.settings, "whub_llm_backend", "hermes")
    assert structuring.default_structuring_runner() is structuring._default_hermes_runner


def test_long_cv_blocks_run_in_parallel_and_keep_source_order(monkeypatch):
    seen_labels = []

    def fake_run_block(text, instructions, comments, first_name, runner, label):
        seen_labels.append(label)
        return {"index": int(label.split("/")[0])}

    blocks = [{"kind": "experience", "text": f"bloc {i}"} for i in range(6)]
    monkeypatch.setattr(structuring.settings, "whub_llm_backend", "openrouter")
    monkeypatch.setattr(structuring.settings, "whub_long_cv_block_parallelism", 3)
    monkeypatch.setattr(structuring, "split_cv_text_into_blocks", lambda _text: blocks)
    monkeypatch.setattr(structuring, "_run_block", fake_run_block)
    monkeypatch.setattr(structuring, "default_structuring_runner", lambda: openrouter_runner)

    captured = {}

    class _Stop(Exception):
        pass

    def fake_assemble(structured_blocks, _first_name):
        captured["order"] = [b["index"] for b in structured_blocks]
        raise _Stop

    monkeypatch.setattr(structuring, "assemble_structured_blocks", fake_assemble)

    with pytest.raises(_Stop):
        structuring.build_whub_json("x" * 20000, "", [], "JEAN", long_cv_threshold=100)

    assert captured["order"] == [1, 2, 3, 4, 5, 6]
    assert sorted(seen_labels) == sorted(f"{i}/6 experience" for i in range(1, 7))
