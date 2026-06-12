from __future__ import annotations

import json
import re
import time
from typing import Any
from unittest.mock import MagicMock

import pytest

from src.content_blocks import ContentBlock, SourceDocument
from src.deterministic_layout_planner import build_deterministic_layout_plan
from src.layout_plan import validate_layout_plan

from src.ai_layout_planner import (
    AIPlannerConfig,
    AIPlannerContractError,
    AIPlannerResult,
    AIProvider,
    build_ai_prompt,
    parse_ai_response,
    run_ai_layout_planner,
)
from src.ai_layout_planner_facade import (
    AIPlannerConfig as FacadeConfig,
    AIPlannerContractError as FacadeError,
    AIPlannerResult as FacadeResult,
    AIProvider as FacadeProvider,
    run_ai_layout_planner as facade_run,
)


def _make_simple_doc() -> SourceDocument:
    return SourceDocument(
        blocks=[
            ContentBlock.from_text("profile", 1, 0, "John Doe", required=True),
            ContentBlock.from_text("skills", 2, 0, "Python, Go", required=True),
            ContentBlock.from_text("experience", 3, 0, "ENG @ Acme", required=True),
            ContentBlock.from_text("education", 4, 0, "MSc CS", required=True),
        ]
    )


class FakeProvider:
    def __init__(self, response: str = "", delay: float = 0.0, exc: Exception | None = None) -> None:
        self._response = response
        self._delay = delay
        self._exc = exc
        self.calls: list[tuple[str, str]] = []

    def complete(self, prompt: str, *, model: str) -> str:
        self.calls.append((prompt, model))
        if self._exc is not None:
            raise self._exc
        if self._delay:
            time.sleep(self._delay)
        return self._response


def _valid_json_response(block_ids: list[str], strategy: str = "natural") -> str:
    return json.dumps(
        {
            "strategy": strategy,
            "page_assignments": {"main": block_ids},
            "variant_density": "normal",
            "rationale": "AI plan",
        }
    )


def _base_config(**overrides: Any) -> AIPlannerConfig:
    data: dict[str, Any] = {
        "enabled": True,
        "model": "gpt-4o-mini",
        "provider_name": "openai",
        "timeout_seconds": 5.0,
        "max_attempts": 1,
        "max_rationale_chars": 280,
    }
    data.update(overrides)
    return AIPlannerConfig(**data)


# 1. test_fallback_when_disabled
def test_fallback_when_disabled() -> None:
    doc = _make_simple_doc()
    config = _base_config(enabled=False)
    result = run_ai_layout_planner(doc, candidate_first_name="Jérémy", provider=FakeProvider(), config=config)
    assert result.used_fallback is True
    assert result.provider_name == "deterministic-fallback"
    assert result.model == "none"
    assert result.error is None


# 2. test_fallback_when_no_provider
def test_fallback_when_no_provider() -> None:
    doc = _make_simple_doc()
    config = _base_config(enabled=True)
    result = run_ai_layout_planner(doc, candidate_first_name="Jérémy", provider=None, config=config)
    assert result.used_fallback is True
    assert result.provider_name == "deterministic-fallback"
    assert result.error is None


# 3. test_provider_returns_valid_proposal
def test_provider_returns_valid_proposal() -> None:
    doc = _make_simple_doc()
    block_ids = [b.id for b in doc.blocks]
    provider = FakeProvider(response=_valid_json_response(block_ids, strategy="natural"))
    config = _base_config(provider_name="test-provider")
    result = run_ai_layout_planner(doc, candidate_first_name="Jérémy", provider=provider, config=config)
    assert result.used_fallback is False
    assert result.proposal.strategy == "natural"
    assert result.provider_name == "test-provider"
    assert result.model == "gpt-4o-mini"
    assert result.error is None
    from src.ai_layout_planner_contract import validate_ai_proposal as _validate
    _validate(result.proposal, doc)


# 4. test_provider_returns_invalid_json
def test_provider_returns_invalid_json() -> None:
    doc = _make_simple_doc()
    provider = FakeProvider(response="not json")
    config = _base_config()
    result = run_ai_layout_planner(doc, candidate_first_name="Jérémy", provider=provider, config=config)
    assert result.used_fallback is True
    assert result.error is not None
    assert "AIPlannerContractError" in result.error


# 5. test_provider_returns_unknown_block_id
def test_provider_returns_unknown_block_id() -> None:
    doc = _make_simple_doc()
    provider = FakeProvider(response=_valid_json_response(["__unknown__"]))
    config = _base_config()
    result = run_ai_layout_planner(doc, candidate_first_name="Jérémy", provider=provider, config=config)
    assert result.used_fallback is True
    assert result.error is not None


# 6. test_provider_returns_missing_required_block
def test_provider_returns_missing_required_block() -> None:
    doc = _make_simple_doc()
    provider = FakeProvider(response=_valid_json_response([doc.blocks[0].id]))
    config = _base_config()
    result = run_ai_layout_planner(doc, candidate_first_name="Jérémy", provider=provider, config=config)
    assert result.used_fallback is True
    assert result.error is not None


# 7. test_provider_raises_exception
def test_provider_raises_exception() -> None:
    doc = _make_simple_doc()
    provider = FakeProvider(exc=RuntimeError("boom"))
    config = _base_config()
    result = run_ai_layout_planner(doc, candidate_first_name="Jérémy", provider=provider, config=config)
    assert result.used_fallback is True
    assert result.error == "RuntimeError"


# 8. test_provider_returns_text_in_rationale
def test_provider_returns_text_in_rationale() -> None:
    doc = _make_simple_doc()
    block_ids = [b.id for b in doc.blocks]
    response = json.dumps(
        {
            "strategy": "natural",
            "page_assignments": {"main": block_ids},
            "variant_density": "normal",
            "rationale": "Mettre Jean Pierre Martin en valeur",
        }
    )
    provider = FakeProvider(response=response)
    config = _base_config()
    result = run_ai_layout_planner(doc, candidate_first_name="Jérémy", provider=provider, config=config)
    assert result.used_fallback is True
    assert result.error is not None


# 9. test_prompt_does_not_leak_full_block_text
def test_prompt_does_not_leak_full_block_text() -> None:
    doc = SourceDocument(
        blocks=[
            ContentBlock.from_text(
                "profile", 1, 0,
                "Email: secret@example.com Phone: 0612345678",
                required=True,
            ),
        ]
    )
    prompt = build_ai_prompt(doc, "Jérémy")
    assert "secret@example.com" not in prompt
    assert "0612345678" not in prompt


# 10. test_prompt_does_not_leak_email_phone_in_blocks
def test_prompt_does_not_leak_email_phone_in_blocks() -> None:
    doc = SourceDocument(
        blocks=[
            ContentBlock.from_text("profile", 1, 0, "john@doe.com LinkedIn: /in/john", required=True),
            ContentBlock.from_text("experience", 2, 0, "Visit https://example.com", required=True),
            ContentBlock.from_text("skills", 3, 0, "Python Call +33123456789", required=True),
        ]
    )
    prompt = build_ai_prompt(doc, "Jérémy")
    for pattern in ["john@doe.com", "/in/john", "https://example.com", "+33123456789"]:
        assert pattern not in prompt, f"leak found: {pattern}"


# 11. test_duration_recorded
def test_duration_recorded() -> None:
    doc = _make_simple_doc()
    block_ids = [b.id for b in doc.blocks]
    provider = FakeProvider(response=_valid_json_response(block_ids), delay=0.05)
    config = _base_config()
    result = run_ai_layout_planner(doc, candidate_first_name="Jérémy", provider=provider, config=config)
    assert result.duration_ms >= 40


# 12. test_facade_reexports
def test_facade_reexports() -> None:
    import src.ai_layout_planner_facade as facade
    assert hasattr(facade, "run_ai_layout_planner")
    assert hasattr(facade, "AIPlannerConfig")
    assert hasattr(facade, "AIPlannerResult")
    assert hasattr(facade, "AIProvider")
    assert hasattr(facade, "AIPlannerContractError")
