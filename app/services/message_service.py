"""Message service -- LLM drafts customer copy AFTER policy selected
`send_message`. It never selects or shapes the intervention.

Privacy: the LLM receives only failure_class, amount, tenure -- no case IDs,
no internal reasoning, no budget info.
"""

from __future__ import annotations

from decimal import Decimal

from app.services.llm_client import (
    LLMParseError,
    MessageOutput,
    complete_structured,
    remember_failure_class,
)

PROMPT = (
    'Write a brief, non-pushy payment recovery message (max 60 words) for a '
    'subscription payment that failed due to "{failure_class}" '
    '(amount Rs {amount}, customer of {tenure} months standing). '
    'Do not mention a discount or a specific amount. '
    'Respond ONLY with JSON: {{"body": "..."}}'
)

STRICT_RETRY_PROMPT = (
    'Your previous answer was not valid JSON. Write the message again for '
    'failure class "{failure_class}". Respond ONLY with JSON: {{"body": "..."}}'
)

FALLBACK_TEMPLATES = {
    "expired_card": (
        "Hi! Your card on file has expired, so your subscription payment "
        "did not go through. Update your payment details anytime to "
        "continue enjoying your service."
    ),
    "insufficient_funds": (
        "Hi! We could not process your subscription payment this time. "
        "Whenever you're ready, retrying from your account page will get "
        "everything back on track."
    ),
    "bank_decline": (
        "Hi! Your bank declined the latest subscription charge. If this "
        "was unexpected, checking with your bank or updating your payment "
        "method will help restore service quickly."
    ),
    "mandate_cancelled": (
        "Hi! Your automatic payment authorization was cancelled, so we "
        "could not collect your subscription. Re-authorizing autopay in "
        "your account settings will resume everything."
    ),
    "unknown": (
        "Hi! We had trouble processing your latest subscription payment. "
        "A quick visit to your payment settings usually fixes it. Sorry "
        "for the interruption!"
    ),
}


def draft_message(failure_class: str, amount: Decimal,
                  tenure_months: int) -> tuple[str, str]:
    """Return (body, source). Falls back to deterministic template if the
    LLM fails validation twice."""
    remember_failure_class(failure_class)
    try:
        out, provider = complete_structured(
            PROMPT.format(failure_class=failure_class, amount=amount,
                          tenure=tenure_months),
            MessageOutput,
            strict_retry_prompt=STRICT_RETRY_PROMPT.format(
                failure_class=failure_class),
        )
        return out.body.strip(), ("llm" if provider != "mock" else "mock")
    except LLMParseError:
        return FALLBACK_TEMPLATES.get(failure_class,
                                      FALLBACK_TEMPLATES["unknown"]), "fallback"
