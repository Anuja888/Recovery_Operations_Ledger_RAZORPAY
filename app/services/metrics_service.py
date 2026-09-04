"""Batch metrics service (spec §13).

All formulas use the batch's stored rows. Ground truth
(`true_recoverable`, `true_would_recover_without_action`) is used HERE --
for evaluation and baseline comparison only -- never by the scorer or the
policy engine.
"""

from __future__ import annotations

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import (
    RECOVERY_INTERVENTIONS,
    BatchRun,
    Case,
    PolicyDecision,
)


def compute_and_store_metrics(db: Session, batch_run: BatchRun,
                              case_ids: list[str]) -> BatchRun:
    cases = db.execute(
        select(Case).where(Case.id.in_(case_ids))
    ).scalars().all()
    decisions = {
        d.case_id: d
        for d in db.execute(
            select(PolicyDecision).where(PolicyDecision.case_id.in_(case_ids))
        ).scalars().all()
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
            baseline_count += 1  # a blind retry-everything would have saved this one

        decision = decisions.get(case.id)
        intervention = decision.intervention if decision else None
        spent = Decimal(str(decision.budget_consumed)) if (
            decision and decision.budget_consumed) else Decimal("0")
        total_cost += spent

        if case.true_recoverable and intervention in RECOVERY_INTERVENTIONS:
            recovered_amount += amount
            recovered_case_count += 1
        if not case.true_recoverable:
            false_positive_cost += spent  # spend on hopeless cases
        if intervention == "stop":
            blocked += 1

    batch_run.total_cases = total_cases
    batch_run.total_at_risk_amount = at_risk
    batch_run.total_recovered_amount = recovered_amount
    batch_run.total_cost = total_cost
    batch_run.net_recovered = recovered_amount - total_cost
    batch_run.recovery_rate = (recovered_case_count / total_cases) if total_cases else 0.0
    batch_run.baseline_recovery_rate = (baseline_count / total_cases) if total_cases else 0.0
    batch_run.false_positive_cost = false_positive_cost
    batch_run.cases_blocked_by_stopping_rules = blocked

    db.add(batch_run)
    db.flush()
    return batch_run


def segment_breakdown(db: Session, batch_run_id: str) -> list[dict]:
    """Recovery rate + cost per failure_class and per prior_failure bucket.

    Uses each case's Diagnosis row (runtime class), not generator truth.
    """
    from app.models import AuditLog

    # cases processed in this batch are linked via the batch summary audit
    # event payload; fall back to all intervened/resolved cases if missing
    summaries = db.execute(
        select(AuditLog).where(AuditLog.event_type == "batch_summary")
    ).scalars().all()
    case_ids: list[str] = []
    for s in summaries:
        if (s.payload or {}).get("batch_run_id") == batch_run_id:
            case_ids = list(s.payload.get("case_ids", []))
            break
    if not case_ids:
        return []

    rows = db.execute(
        select(Case, PolicyDecision, AuditLog)
        .outerjoin(PolicyDecision, PolicyDecision.case_id == Case.id)
        .outerjoin(AuditLog, (AuditLog.case_id == Case.id)
                   & (AuditLog.event_type == "diagnosis"))
        .where(Case.id.in_(case_ids))
    ).all()

    def bucket(pfc: int) -> str:
        return "0" if pfc == 0 else "1-2" if pfc <= 2 else "3-4" if pfc <= 4 else "5+"

    segments: dict[str, dict] = {}
    for case, decision, diagnosis_event in rows:
        fc = (diagnosis_event.payload.get("failure_class", "unknown")
              if diagnosis_event and diagnosis_event.payload else "unknown")
        spent = Decimal(str(decision.budget_consumed)) if (
            decision and decision.budget_consumed) else Decimal("0")
        recovered = bool(
            case.true_recoverable and decision
            and decision.intervention in RECOVERY_INTERVENTIONS
        )
        for key in (f"class:{fc}", f"pfc:{bucket(case.prior_failure_count)}"):
            seg = segments.setdefault(key, {
                "segment": key, "cases": 0, "recovered_cases": 0,
                "recovered_amount": Decimal("0"), "cost": Decimal("0"),
                "net_recovered": Decimal("0"),
            })
            seg["cases"] += 1
            seg["cost"] += spent
            if recovered:
                seg["recovered_cases"] += 1
                seg["recovered_amount"] += Decimal(str(case.amount))
            seg["net_recovered"] = seg["recovered_amount"] - seg["cost"]

        # explicit combined dimension: the documented failure segment is
        # insufficient_funds AND prior_failure_count >= 3 -- surfaced here so
        # the problem is discoverable through the API, not screenshots.
        if fc == "insufficient_funds":
            key = ("class:insufficient_funds|pfc>=3"
                   if case.prior_failure_count >= 3
                   else "class:insufficient_funds|pfc<3")
            seg = segments.setdefault(key, {
                "segment": key, "cases": 0, "recovered_cases": 0,
                "recovered_amount": Decimal("0"), "cost": Decimal("0"),
                "net_recovered": Decimal("0"),
            })
            seg["cases"] += 1
            seg["cost"] += spent
            if recovered:
                seg["recovered_cases"] += 1
                seg["recovered_amount"] += Decimal(str(case.amount))
            seg["net_recovered"] = seg["recovered_amount"] - seg["cost"]

    out = []
    for seg in segments.values():
        n = seg.pop("cases")
        seg["cases"] = n
        seg["recovery_rate"] = round(seg["recovered_cases"] / n, 4) if n else 0.0
        for k in ("cost", "recovered_amount", "net_recovered"):
            seg[k] = float(seg[k])
        out.append(seg)
    out.sort(key=lambda s: s["segment"])
    return out
