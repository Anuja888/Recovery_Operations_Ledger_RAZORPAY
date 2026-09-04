"""Deterministic policy engine -- THE money-decision module.

This module is:
  * pure            (no DB, no network, no clock reads -- time is injected)
  * deterministic   (same inputs -> same decision)
  * unit-testable   (plain dataclasses in, one PolicyDecision out)

The LLM NEVER touches this code path. All interventions that consume money
or contact customers are chosen HERE and only HERE.

Rule order (first match wins), per build spec §9:

  1. low diagnosis confidence          -> escalate
  2. repeated mandate cancellation     -> stop
  3. retry cooldown active (<24h)      -> stop
  4. high recoverability (>= 0.70)     -> retry_now
  5. moderate (0.40..0.69) + budget    -> send_message (deducts budget)
  6. moderate but budget exhausted     -> stop
  7. low recoverability                -> stop

Optional hardened segment rule (the DOCUMENTED FIX, spec §17): when
`segment_send_threshold=0.85` is passed, cases with
failure_class == insufficient_funds AND prior_failure_count >= 3 must score
>= 0.85 before send_message is allowed; otherwise they are stopped. The v1
run passes None (original behaviour) so both batch runs stay reproducible.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta
from decimal import Decimal

# --- tunable thresholds ---
LOW_CONFIDENCE_THRESHOLD = 0.5
REPEATED_FAILURE_MIN = 3
COOLDOWN_PERIOD = timedelta(hours=24)
HIGH_RECOVERABILITY_THRESHOLD = 0.70
MODERATE_RECOVERABILITY_MIN = 0.40


@dataclass(frozen=True)
class DiagnosisInput:
    failure_class: str
    confidence: float


@dataclass(frozen=True)
class ScoreInput:
    recoverability: float


@dataclass(frozen=True)
class CaseInput:
    """Minimal case view. Deliberately EXCLUDES ground-truth fields."""

    case_id: str
    amount: Decimal
    prior_failure_count: int
    customer_tenure_months: int


@dataclass
class BatchBudget:
    """Hard cap on escalation spending for one batch run.

    Spending beyond `cap` is structurally impossible: `try_spend` refuses
    when remaining budget <= cost. Proven by test_budget_never_exceeded.
    """

    cap: Decimal
    spent: Decimal = field(default_factory=lambda: Decimal("0"))

    @property
    def remaining(self) -> Decimal:
        return self.cap - self.spent

    def try_spend(self, cost: Decimal) -> bool:
        if self.remaining <= cost:
            return False
        self.spent += cost
        return True


@dataclass(frozen=True)
class PolicyDecision:
    intervention: str  # retry_now | retry_after_cooldown | send_message | escalate | stop
    reason: str        # mandatory human-readable justification
    budget_consumed: Decimal | None = None


def _stop(reason: str) -> PolicyDecision:
    return PolicyDecision(intervention="stop", reason=reason)


def decide(
    diagnosis: DiagnosisInput,
    score: ScoreInput,
    case: CaseInput,
    budget: BatchBudget,
    last_retry_at: datetime | None = None,
    *,
    now: datetime,
    message_estimated_cost: Decimal = Decimal("300"),
    segment_send_threshold: float | None = None,
) -> PolicyDecision:
    """Return exactly one bounded intervention for a diagnosed, scored case."""

    # Rule 1 -- low diagnosis confidence: never act automatically.
    if diagnosis.confidence < LOW_CONFIDENCE_THRESHOLD:
        return PolicyDecision(
            intervention="escalate",
            reason="low diagnosis confidence, human review required",
        )

    # Rule 2 -- repeated mandate cancellation: retrying cannot work, the
    # customer must re-authorize.
    if (
        case.prior_failure_count >= REPEATED_FAILURE_MIN
        and diagnosis.failure_class == "mandate_cancelled"
    ):
        return _stop(
            "mandate cancelled after repeated failures, retrying is not "
            "viable — requires customer to re-authorize"
        )

    # Rule 3 -- cooldown: a retry was already attempted for this case during
    # the last 24 hours (caller passes the timestamp from audit history).
    if last_retry_at is not None and (now - last_retry_at) < COOLDOWN_PERIOD:
        return _stop("cooldown period active, stopping rule applied")

    # Hardened segment rule (DOCUMENTED FIX). Applied after safety rules,
    # before generic scoring bands.
    in_risky_segment = (
        diagnosis.failure_class == "insufficient_funds"
        and case.prior_failure_count >= REPEATED_FAILURE_MIN
    )
    if segment_send_threshold is not None and in_risky_segment:
        if score.recoverability < segment_send_threshold:
            return _stop(
                "insufficient_funds with repeated failures requires very high "
                f"recoverability (>={segment_send_threshold}) to justify "
                "outreach spend"
            )

    # Rule 4 -- high recoverability.
    if score.recoverability >= HIGH_RECOVERABILITY_THRESHOLD:
        return PolicyDecision(
            intervention="retry_now",
            reason=(
                f"high recoverability ({score.recoverability:.2f} >= "
                f"{HIGH_RECOVERABILITY_THRESHOLD}), immediate retry justified"
            ),
        )

    # Rules 5 & 6 -- moderate recoverability, gated by budget availability.
    if MODERATE_RECOVERABILITY_MIN <= score.recoverability < HIGH_RECOVERABILITY_THRESHOLD:
        if budget.try_spend(message_estimated_cost):
            return PolicyDecision(
                intervention="send_message",
                reason=(
                    f"moderate recoverability ({score.recoverability:.2f}), "
                    f"outreach cost {message_estimated_cost} within batch budget"
                ),
                budget_consumed=message_estimated_cost,
            )
        return _stop("recovery budget exhausted for this batch")

    # Rule 7 -- low recoverability.
    return _stop("low recoverability, action not justified")
