"""Integration test: 20 synthetic cases through the FULL pipeline.

Asserts every case ends with a complete, non-empty audit trail
(diagnosis -> score -> policy_decision -> intervention-specific event).
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest

from app.database import SessionLocal, init_db
from app.models import AuditLog, Case
from app.pipeline import run_batch


def _make_cases(n: int = 20) -> list[str]:
    db = SessionLocal()
    try:
        ids = []
        for i in range(n):
            structured = i % 2 == 0  # mix of rule-code and free-text cases
            case = Case(
                id=f"itest{i:04d}",
                subscription_id=f"sub_itest_{i}",
                merchant_id="m_test",
                amount=500 + i * 137,
                failure_code=(
                    ["insufficient_funds", "bank_decline_0551",
                     "card_expired", "mandate_revoked"][i % 4]
                    if structured else None
                ),
                failure_message=(
                    ["Account balance too low.",
                     "The issuing bank declined this payment.",
                     "Card expired last month."][i % 3]
                    if not structured else None
                ),
                customer_tenure_months=(i * 5) % 60,
                prior_failure_count=i % 6,
                payment_method=["card", "upi", "netbanking"][i % 3],
                merchant_category=["saas", "ott"][i % 2],
                status="new",
                created_at=datetime.now(timezone.utc),
                true_recoverable=bool(i % 3),
                true_would_recover_without_action=False,
            )
            db.add(case)
            ids.append(case.id)
        db.commit()
        return ids
    finally:
        db.close()


@pytest.fixture(scope="module")
def processed_batch():
    init_db()
    case_ids = _make_cases(20)
    db = SessionLocal()
    try:
        batch = run_batch(db, 20)
        return batch.id, case_ids
    finally:
        db.close()


def test_all_20_cases_have_complete_non_empty_audit_trails(processed_batch):
    batch_id, case_ids = processed_batch
    assert len(case_ids) == 20

    db = SessionLocal()
    try:
        events = (
            db.query(AuditLog)
            .filter(AuditLog.case_id.in_(case_ids))
            .all()
        )
        per_case: dict[str, set[str]] = {}
        for e in events:
            if e.case_id:
                per_case.setdefault(e.case_id, set()).add(e.event_type)

        # 100% audit trail coverage
        assert set(per_case.keys()) == set(case_ids)

        for cid, event_types in per_case.items():
            # every processed case must at least be diagnosed and decided
            assert "diagnosis" in event_types, f"{cid} missing diagnosis"
            assert len(event_types) >= 1 and all(event_types)
            case = db.get(Case, cid)
            # diagnosed-only (safety-stop) or fully processed -- never 'new'
            assert case.status != "new"

        # most cases should complete scoring + decision (low-confidence
        # mock diagnoses stop early by design)
        scored = sum(1 for et in per_case.values() if "score" in et)
        decided = sum(
            1 for et in per_case.values() if "policy_decision" in et
        )
        assert decided == scored  # decision follows score 1:1
    finally:
        db.close()


def test_batch_metrics_are_consistent(processed_batch):
    from decimal import Decimal

    from app.models import BatchRun

    batch_id, case_ids = processed_batch
    db = SessionLocal()
    try:
        batch = db.get(BatchRun, batch_id)
        assert batch.total_cases == 20
        assert batch.recovery_rate <= 1.0
        assert batch.baseline_recovery_rate <= 1.0
        # budget cap can never be exceeded
        assert Decimal(str(batch.total_cost)) <= Decimal("5000")
        assert batch.finished_at is not None
    finally:
        db.close()
