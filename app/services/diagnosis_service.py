"""Diagnosis service.

Two paths, per spec §7:

1. structured `failure_code` -> deterministic dict lookup, confidence 1.0,
   source "rule". No LLM involved.
2. free-text `failure_message` -> LLM classification into the fixed failure
   enum with strict schema validation; ONE stricter retry on validation
   failure; deterministic fallback (unknown / 0.0 / rule) if both fail.

Safety stop: confidence below LOW_CONFIDENCE_THRESHOLD (0.5) flags the case
for human review -- it must NOT be auto-scored or auto-intervened. This is
graceful degradation by design.
"""

from __future__ import annotations

from dataclasses import dataclass

from app.config import settings
from app.services.llm_client import (
    DiagnosisOutput,
    LLMParseError,
    complete_structured,
    remember_free_text,
)

# Canonical mapping: structured gateway-style code -> failure class.
FAILURE_CODE_MAP = {
    "card_expired": "expired_card",
    "expired_card": "expired_card",
    "insufficient_funds": "insufficient_funds",
    "nsf": "insufficient_funds",
    "bank_decline_0551": "bank_decline",
    "do_not_honor": "bank_decline",
    "issuer_unavailable": "bank_decline",
    "mandate_revoked": "mandate_cancelled",
    "customer_stopped_mandate": "mandate_cancelled",
}

PROMPT = """Classify the following payment-failure message into exactly one \
failure class: expired_card, insufficient_funds, bank_decline, \
mandate_cancelled, unknown.

Message: "{message}"

Respond ONLY with a JSON object:
{{"failure_class": "...", "confidence": 0.0-1.0, "rationale": "short reason"}}"""

STRICT_RETRY_PROMPT = """Your previous answer was not valid JSON or used an \
unknown failure class. Answer again for message: "{message}"

Allowed failure_class values (choose exactly one): expired_card, \
insufficient_funds, bank_decline, mandate_cancelled, unknown.

Respond ONLY with a JSON object:
{{"failure_class": "...", "confidence": 0.0-1.0, "rationale": "short reason"}}"""


@dataclass(frozen=True)
class DiagnosisResult:
    failure_class: str
    confidence: float
    source: str          # rule | llm | fallback
    rationale: str


def diagnose(failure_code: str | None, failure_message: str | None) -> DiagnosisResult:
    if failure_code:
        fc = FAILURE_CODE_MAP.get(failure_code)
        if fc is not None:
            return DiagnosisResult(
                failure_class=fc, confidence=1.0, source="rule",
                rationale=f"structured failure_code '{failure_code}' mapped deterministically",
            )
        # unknown structured code -> treat as free text below if possible
        if not failure_message:
            return DiagnosisResult(
                failure_class="unknown", confidence=0.0, source="rule",
                rationale=f"unrecognized failure_code '{failure_code}' and no message",
            )

    if not failure_message:
        return DiagnosisResult(
            failure_class="unknown", confidence=0.0, source="rule",
            rationale="no failure information available at all",
        )

    remember_free_text(failure_message)
    try:
        out, provider = complete_structured(
            PROMPT.format(message=failure_message),
            DiagnosisOutput,
            strict_retry_prompt=STRICT_RETRY_PROMPT.format(message=failure_message),
        )
        return DiagnosisResult(
            failure_class=out.failure_class,
            confidence=float(out.confidence),
            source="llm" if provider != "mock" else "mock",
            rationale=out.rationale,
        )
    except LLMParseError:
        # deterministic fallback after retry also failed
        return DiagnosisResult(
            failure_class="unknown", confidence=0.0, source="rule",
            rationale="LLM output failed schema validation twice; "
                      "fell back to unknown (case flagged for review)",
        )


def needs_human_review(confidence: float) -> bool:
    return confidence < settings.low_confidence_threshold
