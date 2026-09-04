"""Minimal API-based LLM client with strict structured-output parsing.

Providers:
  * anthropic / openai -- real API calls (key from env); used for the two
    allowed LLM tasks ONLY: ambiguous-diagnosis classification and customer
    message wording.
  * mock -- deterministic offline fallback (keyword heuristics / template).
    Used in dev and CI so the whole system runs without keys or network.
    Clearly labelled `source="mock"` in outputs and audit payloads.

No SDK dependencies: plain httpx calls. Structured outputs are validated
with Pydantic; invalid output raises LLMParseError so callers can retry /
fall back deterministically.
"""

from __future__ import annotations

import json
import re
from typing import Literal

import httpx
from pydantic import BaseModel, Field, ValidationError

from app.config import settings


class DiagnosisOutput(BaseModel):
    """Strict schema for the diagnosis classification task."""

    failure_class: Literal[
        "expired_card",
        "insufficient_funds",
        "bank_decline",
        "mandate_cancelled",
        "unknown",
    ]
    confidence: float = Field(ge=0.0, le=1.0)
    rationale: str


class MessageOutput(BaseModel):
    """Strict schema for customer-facing recovery copy."""

    body: str = Field(min_length=10)


class LLMParseError(Exception):
    pass


def _extract_json(text: str) -> dict:
    m = re.search(r"\{.*\}", text, re.DOTALL)
    if not m:
        raise LLMParseError("no JSON object found in model output")
    try:
        return json.loads(m.group(0))
    except json.JSONDecodeError as e:
        raise LLMParseError(f"invalid JSON: {e}") from e


# ---------------------------------------------------------------- mock -----

_KEYWORDS = [
    ("expired", "expired_card"), ("expiry", "expired_card"),
    ("balance", "insufficient_funds"), ("funds", "insufficient_funds"),
    ("enough", "insufficient_funds"),
    ("declined", "bank_decline"), ("fraud", "bank_decline"),
    ("issuer", "bank_decline"), ("blocked", "bank_decline"),
    ("mandate", "mandate_cancelled"), ("revoked", "mandate_cancelled"),
    ("autopay", "mandate_cancelled"),
]


def _mock_diagnose(message: str) -> DiagnosisOutput:
    lowered = message.lower()
    hits = [(kw, fc) for kw, fc in _KEYWORDS if kw in lowered]
    # ambiguous text -> genuinely unknown, low confidence (safety path)
    if not hits or len({fc for _, fc in hits}) > 1:
        return DiagnosisOutput(
            failure_class="unknown", confidence=0.3,
            rationale="mock: no unambiguous failure signal in free text",
        )
    fc = hits[0][1]
    return DiagnosisOutput(
        failure_class=fc, confidence=0.9,
        rationale=f"mock: matched keyword pattern for {fc}",
    )


def _mock_message(failure_class: str) -> MessageOutput:
    return MessageOutput(
        body=(
            f"Hi! We noticed your recent subscription payment could not be "
            f"completed ({failure_class.replace('_', ' ')}). When you're "
            f"ready, updating your payment details will restore access "
            f"right away. Thanks!"
        )
    )

# ------------------------------------------------------------- providers ---


def _call_anthropic(prompt: str) -> str:
    resp = httpx.post(
        "https://api.anthropic.com/v1/messages",
        headers={
            "x-api-key": settings.anthropic_api_key,
            "anthropic-version": "2023-06-01",
        },
        json={
            "model": settings.llm_model or "claude-3-5-haiku-latest",
            "max_tokens": 300,
            "messages": [{"role": "user", "content": prompt}],
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["content"][0]["text"]


def _call_openai(prompt: str) -> str:
    resp = httpx.post(
        "https://api.openai.com/v1/chat/completions",
        headers={"Authorization": f"Bearer {settings.openai_api_key}"},
        json={
            "model": settings.llm_model or "gpt-4o-mini",
            "messages": [{"role": "user", "content": prompt}],
            "response_format": {"type": "json_object"},
        },
        timeout=30,
    )
    resp.raise_for_status()
    return resp.json()["choices"][0]["message"]["content"]


def complete_structured(prompt: str, schema_model: type[BaseModel], *,
                        strict_retry_prompt: str | None = None):
    """Call the configured provider and validate against `schema_model`.

    Raises LLMParseError if the (possibly retried with stricter
    instructions) response still fails validation. Caller decides fallback.
    """
    for attempt, p in enumerate([prompt, strict_retry_prompt or prompt]):
        if settings.llm_provider == "anthropic":
            raw = _call_anthropic(p)
        elif settings.llm_provider == "openai":
            raw = _call_openai(p)
        else:  # mock provider never fails parsing
            if schema_model is DiagnosisOutput:
                return _mock_diagnose(_last_free_text(p)), "mock"
            return _mock_message(_last_failure_class(p)), "mock"
        try:
            return schema_model.model_validate_json(raw) \
                if raw.strip().startswith("{") else \
                schema_model(**_extract_json(raw)), (
                    "anthropic" if settings.llm_provider == "anthropic" else "openai")
        except (ValidationError, LLMParseError):
            if attempt == 1:
                raise LLMParseError("structured output failed twice")


# helpers so the mock provider can react to the actual input ----------------

_LAST_FREE_TEXT: str = ""


def remember_free_text(text: str) -> None:
    global _LAST_FREE_TEXT
    _LAST_FREE_TEXT = text


def _last_free_text(_prompt: str) -> str:
    return _LAST_FREE_TEXT


_LAST_FAILURE_CLASS: str = "unknown"


def remember_failure_class(fc: str) -> None:
    global _LAST_FAILURE_CLASS
    _LAST_FAILURE_CLASS = fc


def _last_failure_class(_prompt: str) -> str:
    return _LAST_FAILURE_CLASS
