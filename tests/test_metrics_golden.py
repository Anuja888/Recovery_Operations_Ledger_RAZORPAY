"""Metrics golden test: one hand-calculated fixture of five cases.

Fixture design (amounts/costs chosen for easy arithmetic):

| case | true_recoverable | true_wo_action | intervention | amount | cost |
|------|------------------|----------------|--------------|--------|------|
| c1   | True             | False          | retry_now    | 1000   | 0    |
| c2   | True             | True           | send_message | 2000   | 300  |
| c3   | False            | True           | retry_now    | 500    | 0    |
| c4   | False            | False          | send_message | 700    | 300  |
| c5   | True             | False          | stop         | 900    | 0    |

Expected:
  total_at_risk        = 1000+2000+500+700+900            = 5100
  total_recovered      = c1+c2 (true & action) = 1000+2000 = 3000
                       (c5 stopped -> not recovered; c3,c4 not recoverable)
  total_cost           = 300+300                          = 600
  net_recovered        = 3000-600                         = 2400
  recovery_rate        = 2/5                              = 0.40
  baseline_rate        = c2+c3 would recover w/o action   = 2/5 = 0.40
  false_positive_cost  = spend on not-recoverable (c4)     = 300
  cases_blocked        = c5                                = 1
"""

from __future__ import annotations

from decimal import Decimal

import pytest

from app.models import BatchRun, Case, PolicyDecision
from app.services.metrics_service import compute_and_store_metrics


@pytest.fixture
def five_case_fixture(db_session):
    specs = [
        ("c1", True, False, "retry_now", "1000", "0"),
        ("c2", True, True, "send_message", "2000", "300"),
        ("c3", False, True, "retry_now", "500", "0"),
        ("c4", False, False, "send_message", "700", "300"),
        ("c5", True, False, "stop", "900", "0"),
    ]
    for cid, tr, twr, interv, amount, cost in specs:
        db_session.add(Case(
            id=cid,
            subscription_id=f"sub_{cid}",
            merchant_id="m_test",
            amount=Decimal(amount),
            failure_code="insufficient_funds",
            customer_tenure_months=10,
            prior_failure_count=1,
            payment_method="card",
            merchant_category="saas",
            status="resolved" if interv != "stop" else "stopped",
            true_recoverable=tr,
            true_would_recover_without_action=twr,
        ))
        db_session.add(PolicyDecision(
            case_id=cid, intervention=interv, reason="fixture",
            budget_consumed=Decimal(cost),
        ))
    db_session.commit()
    return [s[0] for s in specs]


def test_golden_metrics(db_session, five_case_fixture):
    case_ids = five_case_fixture
    batch = BatchRun()
    db_session.add(batch)
    db_session.flush()

    result = compute_and_store_metrics(db_session, batch, case_ids)

    assert result.total_cases == 5
    assert result.total_at_risk_amount == Decimal("5100")
    assert result.total_recovered_amount == Decimal("3000")
    assert result.total_cost == Decimal("600")
    assert result.net_recovered == Decimal("2400")
    assert result.recovery_rate == pytest.approx(0.40)
    assert result.baseline_recovery_rate == pytest.approx(0.40)
    assert result.false_positive_cost == Decimal("300")
    assert result.cases_blocked_by_stopping_rules == 1
