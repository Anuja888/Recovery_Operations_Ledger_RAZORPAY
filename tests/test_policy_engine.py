"""Policy engine tests: every rule branch + budget/cooldown/stopping invariants."""

from __future__ import annotations

import random
from datetime import datetime, timedelta, timezone
from decimal import Decimal

import pytest

from app.services.policy_engine import (
    BatchBudget,
    CaseInput,
    DiagnosisInput,
    ScoreInput,
    decide,
)

NOW = datetime(2026, 8, 25, 12, 0, tzinfo=timezone.utc)


def mk_diagnosis(fc="insufficient_funds", conf=0.95):
    return DiagnosisInput(failure_class=fc, confidence=conf)


def mk_score(r=0.5):
    return ScoreInput(recoverability=r)


def mk_case(pfc=1, amount="1000"):
    return CaseInput(
        case_id="c_test",
        amount=Decimal(amount),
        prior_failure_count=pfc,
        customer_tenure_months=12,
    )


def decide_simple(fc="insufficient_funds", conf=0.95, r=0.5, pfc=1,
                  budget_cap="5000", last_retry_at=None, cost="300",
                  segment_threshold=None):
    budget = BatchBudget(cap=Decimal(budget_cap))
    decision = decide(
        mk_diagnosis(fc, conf), mk_score(r), mk_case(pfc), budget,
        last_retry_at, now=NOW, message_estimated_cost=Decimal(cost),
        segment_send_threshold=segment_threshold,
    )
    return decision, budget


# ---------- Rule 1: low diagnosis confidence ----------
def test_rule1_low_confidence_escalates():
    d, _ = decide_simple(conf=0.49, r=0.9)
    assert d.intervention == "escalate"
    assert "human review" in d.reason


def test_rule1_boundary_confidence_exactly_half_is_actionable():
    d, _ = decide_simple(conf=0.50, r=0.85)
    assert d.intervention == "retry_now"


# ---------- Rule 2: repeated mandate cancellation ----------
def test_rule2_mandate_cancelled_repeated_stops_even_with_perfect_score():
    d, _ = decide_simple(fc="mandate_cancelled", pfc=3, r=0.99)
    assert d.intervention == "stop"
    assert "re-authorize" in d.reason


def test_rule2_mandate_first_failure_not_stopped_by_rule2():
    d, _ = decide_simple(fc="mandate_cancelled", pfc=1, r=0.5)
    assert d.intervention == "send_message"


def test_mandate_cancelled_never_retried_across_scores_and_budgets():
    for r in (0.0, 0.3, 0.5, 0.69, 0.7, 0.99, 1.0):
        d, _ = decide_simple(fc="mandate_cancelled", pfc=5, r=r,
                             budget_cap="100000")
        assert d.intervention == "stop"
        if r >= 0.4:
            assert "mandate cancelled" in d.reason


# ---------- Rule 3: cooldown ----------
def test_rule3_recent_retry_triggers_cooldown_stop():
    recent = NOW - timedelta(hours=23, minutes=59)
    d, _ = decide_simple(r=0.9, last_retry_at=recent)
    assert d.intervention == "stop"
    assert "cooldown" in d.reason


def test_rule3_old_retry_beyond_24h_allows_intervention():
    old = NOW - timedelta(hours=24, minutes=1)
    d, _ = decide_simple(r=0.9, last_retry_at=old)
    assert d.intervention == "retry_now"


def test_rule3_cooldown_applies_before_spending_budget():
    recent = NOW - timedelta(hours=1)
    _, budget = decide_simple(r=0.5, last_retry_at=recent)
    assert budget.spent == Decimal("0")


# ---------- Rules 4/5/6/7: scoring bands + budget ----------
def test_rule4_high_recoverability_retries_without_cost():
    d, budget = decide_simple(r=0.70)
    assert d.intervention == "retry_now"
    assert d.budget_consumed is None
    assert budget.spent == Decimal("0")


def test_rule5_moderate_with_budget_sends_message_and_deducts():
    d, budget = decide_simple(r=0.55, budget_cap="5000", cost="300")
    assert d.intervention == "send_message"
    assert d.budget_consumed == Decimal("300")
    assert budget.spent == Decimal("300")
    assert budget.remaining == Decimal("4700")


def test_rule6_moderate_without_budget_stops():
    d, _ = decide_simple(r=0.55, budget_cap="299", cost="300")
    assert d.intervention == "stop"
    assert "budget exhausted" in d.reason


def test_rule7_low_recoverability_stops():
    d, _ = decide_simple(r=0.39)
    assert d.intervention == "stop"
    assert "low recoverability" in d.reason


# ---------- Documented-fix segment rule ----------
def test_segment_fix_blocks_low_scored_risky_segment():
    d, _ = decide_simple(fc="insufficient_funds", pfc=3, r=0.55,
                         segment_threshold=0.85)
    assert d.intervention == "stop"


def test_segment_fix_allows_exceptional_score():
    d, _ = decide_simple(fc="insufficient_funds", pfc=3, r=0.86,
                         segment_threshold=0.85)
    assert d.intervention == "retry_now"


def test_segment_fix_does_not_affect_other_segments():
    d, _ = decide_simple(fc="bank_decline", pfc=3, r=0.55,
                         segment_threshold=0.85)
    assert d.intervention == "send_message"


# ---------- Budget invariant over a full random batch ----------
@pytest.mark.parametrize("seed", [1, 42, 1337])
def test_budget_never_exceeded_over_random_batch(seed):
    rng = random.Random(seed)
    cap = Decimal("5000")
    cost = Decimal("300")
    budget = BatchBudget(cap=cap)

    interventions = []
    for i in range(500):
        fc = rng.choice(
            ["expired_card", "insufficient_funds", "bank_decline",
             "mandate_cancelled", "unknown"]
        )
        conf = rng.uniform(0, 1)
        r = rng.random()
        pfc = rng.randint(0, 5)
        last_retry = (
            NOW - timedelta(hours=rng.uniform(0, 48))
            if rng.random() < 0.15 else None
        )
        d = decide(
            mk_diagnosis(fc, conf), mk_score(r),
            CaseInput(case_id=f"c{i}", amount=Decimal(rng.randint(100, 50000)),
                      prior_failure_count=pfc,
                      customer_tenure_months=rng.randint(1, 60)),
            budget, last_retry, now=NOW,
            message_estimated_cost=cost,
        )
        interventions.append(d.intervention)
        assert budget.spent <= cap, "budget cap violated!"

    assert "send_message" in interventions  # batch exercised the spending path
    assert budget.spent <= cap


def test_remaining_budget_exact_fit_is_refused():
    """remaining <= cost means refuse (spec: remaining > cost to act)."""
    budget = BatchBudget(cap=Decimal("600"))
    assert budget.try_spend(Decimal("300"))          # 600 -> 300
    assert not budget.try_spend(Decimal("300"))      # remaining == cost -> refuse
    assert budget.spent == Decimal("300")


# ---------- determinism / purity ----------
def test_same_inputs_same_decision():
    kwargs = dict(fc="bank_decline", conf=0.8, r=0.55, pfc=2, cost="250")
    d1, b1 = decide_simple(**kwargs)
    d2, b2 = decide_simple(**kwargs)
    assert d1 == d2
    assert b1.spent == b2.spent
