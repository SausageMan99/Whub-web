"""Redacted CV quality report builder and source profiler.

This module is the foundation of the W hub CV Factory auto-evaluation loop.
Its only job is to produce deterministic, fully redacted quality reports and
classify the source profile before any model call happens.

Hard rules:
- The module never persists raw email, phone, LinkedIn, GitHub, or generic
  URLs into the produced report. Such values are rejected by
  ``assert_quality_report_is_redacted``.
- Public helpers expose counts, codes, stages, profile names and short
  non-sensitive labels. Snippets longer than 120 chars are truncated.
- Coarse scores are kept between 0 and 100 inclusive.
- The module is dependency-free (stdlib only) so it can be imported from any
  worker test or smoke script.
"""
from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Any

# Pattern kept conservative: matches the same contact surfaces as
# ``qa.CONTACT_PATTERNS`` but expressed at the JSON level for redaction
# enforcement. False positives are acceptable here because we only refuse to
# persist matching strings; the report itself never carries source snippets.
CONTACT_VALUE_RE = re.compile(
    r"(?:[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,})"
    r"|(?:\+33|\b0[67])(?:[ .-]?\d{2}){4}\b"
    r"|(?:linkedin\.com/|github\.com/|https?://|www\.)",
    re.I,
)

VALID_SOURCE_PROFILES = {
    "normal",
    "senior_long",
    "ats",
    "scanned",
    "two_column",
    "graphic",
    "risky",
    "unknown",
}

_SAFE_CODE_RE = re.compile(r"[^a-z0-9_:-]+")


def _bounded_score(value: int | float) -> int:
    return max(0, min(100, int(round(float(value)))))


def _safe_code(value: str) -> str:
    cleaned = _SAFE_CODE_RE.sub("_", str(value or "").strip().lower())
    return cleaned[:80] or "unknown"


def _looks_like_raw_contact(value: Any) -> bool:
    """Recursively walk a JSON-like value to detect raw contact patterns."""
    if isinstance(value, str):
        return bool(CONTACT_VALUE_RE.search(value))
    if isinstance(value, dict):
        return any(_looks_like_raw_contact(v) for v in value.values())
    if isinstance(value, list):
        return any(_looks_like_raw_contact(v) for v in value)
    return False


def assert_quality_report_is_redacted(report: dict[str, Any]) -> None:
    """Raise ``ValueError`` if the report embeds raw contact-like values."""
    if _looks_like_raw_contact(report):
        raise ValueError(
            "quality report contains raw contact-like value; redaction enforced"
        )


def classify_source_profile(text: str) -> dict[str, Any]:
    """Return a deterministic source profile classification.

    The classifier only inspects the raw extracted text. It is intentionally
    simple and routing-only; it must not be used to rewrite content.
    """
    normalized = "\n".join(line.strip() for line in (text or "").splitlines() if line.strip())
    lower = normalized.lower()
    chars = len(normalized)
    lines = normalized.splitlines()
    mission_markers = len(
        re.findall(
            r"\b(?:mission|projet|client|exp[ée]rience|consultant|d[ée]veloppeur|architecte)\b",
            lower,
        )
    )
    ats_markers = len(
        re.findall(
            r"\b(?:tjm|disponibilit[ée]|mobilit[ée]|permis|salaire|contrat)\b",
            lower,
        )
    )
    short_line_ratio = (
        sum(1 for line in lines if len(line) <= 18) / max(1, len(lines))
    )

    # Order matters: ATS markers (TJM, Disponibilité, Mobilité, Permis, …) are
    # a strong explicit signal that this is a jobboard export, not a poorly
    # extracted scan. Only fall back to ``scanned`` when the text is too short
    # to make any other decision and carries no ATS signal.
    if ats_markers >= 3:
        profile = "ats"
    elif chars < 250 and ats_markers == 0:
        profile = "scanned"
    elif chars > 9000 or mission_markers >= 10:
        profile = "senior_long"
    elif short_line_ratio > 0.58 and len(lines) > 45:
        profile = "two_column"
    else:
        profile = "normal"

    return {
        "profile": profile,
        "chars": chars,
        "line_count": len(lines),
        "mission_markers": mission_markers,
        "ats_markers": ats_markers,
        "short_line_ratio": round(short_line_ratio, 3),
    }


def should_require_human_review(profile: dict[str, Any]) -> bool:
    """Return True if the source profile suggests the worker should not auto-generate."""
    source_profile = str(profile.get("profile") or "unknown")
    chars = int(profile.get("chars") or 0)
    line_count = int(profile.get("line_count") or 0)
    if source_profile == "scanned" and chars < 500:
        return True
    if chars < 250 or line_count < 5:
        return True
    return False


@dataclass
class QualityReportBuilder:
    request_id: str
    source_profile: str = "unknown"
    scores: dict[str, int] = field(default_factory=dict)
    metrics: dict[str, Any] = field(default_factory=dict)
    hard_blockers: list[dict[str, Any]] = field(default_factory=list)
    soft_warnings: list[dict[str, Any]] = field(default_factory=list)

    def set_source_profile(self, profile: str) -> None:
        self.source_profile = profile if profile in VALID_SOURCE_PROFILES else "unknown"

    def add_score(self, name: str, value: int | float) -> None:
        self.scores[_safe_code(name)] = _bounded_score(value)

    def add_metric(self, name: str, value: Any) -> None:
        key = _safe_code(name)
        if isinstance(value, (int, float, bool)) or value is None:
            self.metrics[key] = value
        elif isinstance(value, str):
            if _looks_like_raw_contact(value):
                # Refuse to persist; downgrade to a count of 1 so the metric
                # still surfaces that something was detected upstream.
                self.metrics[key] = 1
                return
            self.metrics[key] = value[:120]

    def add_hard_blocker(self, code: str, stage: str, **extra: Any) -> None:
        item = {"code": _safe_code(code), "stage": _safe_code(stage)}
        item.update(
            {
                k: v
                for k, v in extra.items()
                if isinstance(v, (int, float, bool)) or v is None
            }
        )
        self.hard_blockers.append(item)

    def add_soft_warning(self, code: str, stage: str, **extra: Any) -> None:
        item = {"code": _safe_code(code), "stage": _safe_code(stage)}
        item.update(
            {
                k: v
                for k, v in extra.items()
                if isinstance(v, (int, float, bool)) or v is None
            }
        )
        self.soft_warnings.append(item)

    def to_dict(self, stage: str) -> dict[str, Any]:
        report: dict[str, Any] = {
            "schema_version": 1,
            "request_id": self.request_id,
            "source_profile": self.source_profile,
            "stage": _safe_code(stage),
            "scores": {
                "extraction": self.scores.get("extraction", 0),
                "fidelity": self.scores.get("fidelity", 0),
                "layout": self.scores.get("layout", 0),
                "overall": self.scores.get("overall", 0),
            },
            "hard_blockers": list(self.hard_blockers),
            "soft_warnings": list(self.soft_warnings),
            "metrics": dict(self.metrics),
            "redaction": {
                "contains_raw_contact_values": False,
                "contains_source_snippets": False,
            },
        }
        # Promote any extra named scores under their safe slug.
        for name, value in self.scores.items():
            if name not in {"extraction", "fidelity", "layout", "overall"}:
                report["scores"][name] = value
        assert_quality_report_is_redacted(report)
        return report
