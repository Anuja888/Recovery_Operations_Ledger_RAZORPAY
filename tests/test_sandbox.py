"""Tests for POST /sandbox/simulate."""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.database import init_db
from app.models import (
    AuditLog,
    BatchRun,
    Case,
    PolicyDecision,
)
from app.pipeline import run_batch
from app.routes import post_sandbox_simulate
from app.schemas import SandboxRequest


def _make_cases(db, n: int = 50) -> list[str]:
    ids = []
    for i in range(n):
        case = Case(
            id=f"sandbox{i:04d}",
            subscription_id=f"sub_sandbox_{i}",
            merchant_id="m_sandbox",
            amount=500 + i * 137,
            failure_code="insufficient_funds",
            customer_tenure_months=(i * 5) % 60,
            prior_failure_count=i % 6,
            payment_method="card",
            merchant_category="saas",
            status="new",
            true_recoverable=bool(i % 3),
            true_would_recover_without_action=False,
        )
        db.add(case)
        ids.append(case.id)
    db.commit()
    return ids


def _count_rows(db):
    return {
        "cases": db.query(Case).count(),
        "policy_decisions": db.query(PolicyDecision).count(),
        "audit_logs": db.query(AuditLog).count(),
        "batch_runs": db.query(BatchRun).count(),
    }


def test_sandbox_no_side_effects(db_session):
    init_db()
    case_ids = _make_cases(db_session, 50)
    run_batch(db_session, 50)
    db_session.commit()
    before = _count_rows(db_session)

    req1 = SandboxRequest(segment_send_threshold=0.85, budget_cap=5000.0,
                          message_estimated_cost=300.0, sample_size=50)
    post_sandbox_simulate(req1, db_session)
    db_session.commit()
    mid = _count_rows(db_session)
    assert mid == before

    req2 = SandboxRequest(segment_send_threshold=0.70, budget_cap=3000.0,
                          message_estimated_cost=200.0, sample_size=50)
    post_sandbox_simulate(req2, db_session)
    db_session.commit()
    after = _count_rows(db_session)
    assert after == before


def test_sandbox_matches_engine(db_session):
    init_db()
    case_ids = _make_cases(db_session, 50)
    batch = run_batch(db_session, 50, segment_send_threshold=0.85)
    db_session.commit()

    req = SandboxRequest(segment_send_threshold=0.85, budget_cap=5000.0,
                         message_estimated_cost=300.0, sample_size=50)
    resp = post_sandbox_simulate(req, db_session)

    assert resp.total_cases == batch.total_cases
    assert abs(resp.total_at_risk_amount - float(batch.total_at_risk_amount)) < 0.01
    assert abs(resp.total_recovered_amount - float(batch.total_recovered_amount)) < 0.01
    assert abs(resp.total_cost - float(batch.total_cost)) < 0.01
    assert abs(resp.net_recovered - float(batch.net_recovered)) < 0.01
    assert abs(resp.recovery_rate - batch.recovery_rate) < 0.001
    assert abs(resp.baseline_recovery_rate - batch.baseline_recovery_rate) < 0.001
    assert abs(resp.false_positive_cost - float(batch.false_positive_cost)) < 0.01
    assert resp.cases_blocked_by_stopping_rules == batch.cases_blocked_by_stopping_rules
