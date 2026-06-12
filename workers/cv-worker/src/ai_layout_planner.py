from __future__ import annotations

import json
import re
import time
from dataclasses import dataclass
from datetime import datetime, UTC
from typing import Any, Protocol

from pydantic import ValidationError

from src.ai_layout_planner_contract import (
    AIProposedLayout,
    AIPlannerContractError,
    ALLOWED_STRATEGIES,
    AUTHORIZED_ZONES,
    validate_ai_proposal,
)
from src.content_blocks import SourceDocument
from src.deterministic_layout_planner import build_deterministic_layout_plan


class AIProvider(Protocol):
    def complete(self, prompt: str, *, model: str) -> str: ...


_RE_PII = re.compile(
    r"(?:"
    r"[a-zA-Z0-9._%+\-]+@[a-zA-Z0-9.\-]+\.[a-zA-Z]{2,}"
    r"|(?:\+?\d[\d\-().\s]{7,}\d)"
    r"|(?:https?://[^\s]+)"
    r"|(?:linkedin\.com/[^\s]+)"
    r"|(?:/(?:in|pub)/[a-zA-Z0-9_-]+)"
    r")",
    re.IGNORECASE,
)

_RE_RATIONALE_CONTENT_LIKE = re.compile(
    r"(?:\b[A-ZÀ-ÖØ-Þ][a-zà-öø-ÿ]+\b[\s]+){2,}",
    re.UNICODE,
)


def _preview(text: str, max_chars: int = 80) -> str:
    cleaned = text.replace("\r", " ").replace("\n", " ").strip()
    cleaned = _RE_PII.sub("[REDACTED]", cleaned)
    if len(cleaned) > max_chars:
        cleaned = cleaned[: max_chars - 3] + "..."
    return cleaned


def build_ai_prompt(document: SourceDocument, candidate_first_name: str) -> str:
    blocks_md = []
    for block in document.ordered_blocks():
        preview = _preview(block.text)
        line = (
            f"- id=`{block.id}` | type={block.type} | source_order={block.source_order}"
            f" | char_count={block.char_count} | required={block.required}"
            f" | preview={preview}"
        )
        blocks_md.append(line)

    prompt = f"""\
Tu es un layout planner. Tu NE crées JAMAIS de texte. Tu ne proposes QUE une stratégie et des assignments de block_id existants.

Règles strictes:
- INTERDIT d'inventer du texte, d'inventer des block_id, ou de modifier le contenu des blocs.
- Utilise UNIQUEMENT les block_id listés ci-dessous.
- candidate_first_name autorisé dans le rendu: "{candidate_first_name}".

Blocs connus (preview uniquement, texte complet interdit de réinjection):
""" + "\n".join(blocks_md) + """

Réponds UNIQUEMENT par un JSON strict (pas de markdown, pas ```), avec exactement ces clés:
{
  "strategy": "natural" | "compact" | "sidebar_heavy" | "experience_first" | "deterministic_content_preserving",
  "page_assignments": {"header": [...], "main": [...], "right_sidebar": [...], "left_sidebar": [...], "footer": [...]},
  "variant_density": "comfortable" | "normal" | "compact",
  "rationale": string (max 280 chars, JUSTIFICATION seulement, JAMAIS contenu source)
}
"""
    return prompt


@dataclass
class AIPlannerConfig:
    enabled: bool = False
    model: str = "gpt-4o-mini"
    provider_name: str = "openai"
    timeout_seconds: float = 5.0
    max_attempts: int = 1
    max_rationale_chars: int = 280


@dataclass
class AIPlannerResult:
    proposal: AIProposedLayout
    used_fallback: bool
    provider_name: str
    model: str
    duration_ms: int
    error: str | None


def parse_ai_response(raw: str, *, known_block_ids: set[str]) -> dict[str, Any]:
    cleaned = raw.strip()
    if cleaned.startswith("```"):
        lines = cleaned.splitlines()
        if lines[0].lower().startswith("```json"):
            lines = lines[1:]
        elif lines[0].lower().startswith("```"):
            lines = lines[1:]
        if lines and lines[-1].strip() == "```":
            lines = lines[:-1]
        cleaned = "\n".join(lines).strip()

    try:
        data = json.loads(cleaned)
    except json.JSONDecodeError as exc:
        raise AIPlannerContractError(f"invalid JSON from provider: {exc}") from exc

    if not isinstance(data, dict):
        raise AIPlannerContractError("provider response must be a JSON object")

    required_keys = {"strategy", "page_assignments", "variant_density", "rationale"}
    missing = required_keys - data.keys()
    if missing:
        raise AIPlannerContractError(f"missing keys in provider response: {sorted(missing)}")

    if data.get("strategy") not in ALLOWED_STRATEGIES:
        raise AIPlannerContractError(f"invalid strategy in provider response: {data.get('strategy')}")

    if not isinstance(data.get("page_assignments"), dict):
        raise AIPlannerContractError("page_assignments must be a dict")

    for zone, ids in data.get("page_assignments", {}).items():
        if zone not in AUTHORIZED_ZONES:
            raise AIPlannerContractError(f"unauthorized zone in provider response: {zone}")
        if not isinstance(ids, list):
            raise AIPlannerContractError("page_assignments values must be lists")
        for block_id in ids:
            if block_id not in known_block_ids:
                raise AIPlannerContractError(f"unknown block id in provider response: {block_id}")

    if data.get("variant_density") not in {"comfortable", "normal", "compact"}:
        raise AIPlannerContractError("invalid variant_density in provider response")

    if not isinstance(data.get("rationale"), str):
        raise AIPlannerContractError("rationale must be a string")

    return data


def _fallback_result(document: SourceDocument, error: str | None, *, start: float) -> AIPlannerResult:
    plan = build_deterministic_layout_plan(document)
    proposal = AIProposedLayout.from_deterministic_plan(
        plan,
        document,
        provider="deterministic-fallback",
        model="none",
    )
    return AIPlannerResult(
        proposal=proposal,
        used_fallback=True,
        provider_name="deterministic-fallback",
        model="none",
        duration_ms=int((time.monotonic() - start) * 1000),
        error=error,
    )


def run_ai_layout_planner(
    document: SourceDocument,
    *,
    candidate_first_name: str,
    provider: AIProvider | None,
    config: AIPlannerConfig,
) -> AIPlannerResult:
    if not config.enabled or provider is None:
        return _fallback_result(document, None, start=time.monotonic())

    known = {block.id for block in document.blocks}
    t0 = time.monotonic()
    try:
        prompt = build_ai_prompt(document, candidate_first_name)
        raw = provider.complete(prompt, model=config.model)
        parsed = parse_ai_response(raw, known_block_ids=known)
        proposal = AIProposedLayout(
            **parsed,
            ai_provider=config.provider_name,
            ai_model=config.model,
            proposed_at=datetime.now(UTC),
        )
        validate_ai_proposal(proposal, document)
        if _RE_PII.search(proposal.rationale) or _RE_RATIONALE_CONTENT_LIKE.search(proposal.rationale):
            raise AIPlannerContractError("rationale contains content or PII")
        return AIPlannerResult(
            proposal=proposal,
            used_fallback=False,
            provider_name=config.provider_name,
            model=config.model,
            duration_ms=int((time.monotonic() - t0) * 1000),
            error=None,
        )
    except ValidationError:
        raise
    except Exception as exc:
        error = f"{type(exc).__name__}"
        return _fallback_result(document, error, start=t0)
