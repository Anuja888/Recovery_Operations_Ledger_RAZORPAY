"""Sandbox service — side-effect-free replay of the policy engine.

Selects already-diagnosed/scored cases, re-runs only `policy_engine.decide`
with caller-supplied thresholds, and returns computed metrics WITHOUT writing
anything to the database.
"""

from __future__ import annotations

from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    RECOVERY_INTERVENTIONS,
    Case,
    Diagnosis,
    PolicyDecision,
    Score,
)
from app.services.audit_service import get_recent_retry_event
from app.services.metrics_service import compute_and_store_metrics
from app.services.policy_engine import BatchBudget, CaseInput, DiagnosisInput, ScoreInput, decide


def simulate(
    db: Session,
    sample_size: int = 300,
    *,
    budget_cap: float = 5000.0,
    message_estimated_cost: float = 300.0,
    segment_send_threshold: float | None = 0.85,
) -> dict:
    now = datetime.now(timezone.utc)

    cases = db.execute(
        select(Case)
        .where(Case.status != "new")
        .order_by(Case.id)
        .limit(sample_size)
    ).scalars().all()

    if not cases:
        return {
            "total_cases": 0,
            "total_at_risk_amount": 0.0,
            "total_recovered_amount": 0.0,
            "total_cost": 0.0,
            "net_recovered": 0.0,
            "recovery_rate": 0.0,
            "baseline_recovery_rate": 0.0,
            "false_positive_cost": 0.0,
            "cases_blocked_by_stopping_rules": 0,
        }

    case_ids = [c.id for c in cases]
    diagnoses = {
        d.case_id: d
        for d in db.execute(
            select(Diagnosis).where(Diagnosis.case_id.in_(case_ids))
        ).scalars().all()
    }
    scores = {
        s.case_id: s
        for s in db.execute(
            select(Score).where(Score.case_id.in_(case_ids))
        ).scalars().all()
    }

    budget = BatchBudget(cap=Decimal(str(budget_cap)))
    decisions: dict[str, dict] = {}

    for case in cases:
        diag = diagnoses.get(case.id)
        score_row = scores.get(case.id)
        if not diag or not score_row:
            continue

        last_retry_at = get_recent_retry_event(db, case.id, now)

        decision = decide(
            diagnosis=DiagnosisInput(
                failure_class=diag.failure_class,
                confidence=diag.confidence,
            ),
            score=ScoreInput(
                recoverability=score_row.recoverability,
            ),
            case=CaseInput(
                case_id=case.id,
                amount=case.amount,
                prior_failure_count=case.prior_failure_count,
                customer_tenure_months=case.customer_tenure_months,
            ),
            budget=budget,
            last_retry_at=last_retry_at,
            now=now,
            message_estimated_cost=Decimal(str(message_estimated_cost)),
            segment_send_threshold=segment_send_threshold,
        )
        decisions[case.id] = {
            "intervention": decision.intervention,
            "reason": decision.reason,
            "budget_consumed": decision.budget_consumed,
        }

    total_cases = len(cases)
    at_risk = Decimal("0")
    recovered_amount = Decimal("0")
    recovered_case_count = 0
    total_cost = Decimal("0")
    false_positive_cost = Decimal("0")
    blocked = 0
    baseline_count = 0

    for case in cases:
        amount = Decimal(str(case.amount))
        at_risk += amount

        if case.true_would_recover_without_action:
            baseline_count += 1

        decision = decisions.get(case.id)
        intervention = decision["intervention"] if decision else None
        spent = Decimal(str(decision["budget_consumed"])) if (
            decision and decision["budget_consumed"]
        ) else Decimal("0")
        total_cost += spent

        if case.true_recoverable and intervention in RECOVERY_INTERVENTIONS:
            recovered_amount += amount
            recovered_case_count += 1
        if not case.true_recoverable:
            false_positive_cost += spent
        if intervention == "stop":
            blocked += 1

    return {
        "total_cases": total_cases,
        "total_at_risk_amount": float(at_risk),
        "total_recovered_amount": float(recovered_amount),
        "total_cost": float(total_cost),
        "net_recovered": float(recovered_amount - total_cost),
        "recovery_rate": (recovered_case_count / total_cases) if total_cases else 0.0,
        "baseline_recovery_rate": (baseline_count / total_cases) if total_cases else 0.0,
        "false_positive_cost": float(false_positive_cost),
        "cases_blocked_by_stopping_rules": blocked,
    }
