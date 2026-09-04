"""Tests for GET /batches/{batch_id}/ai-usage."""

from __future__ import annotations

from decimal import Decimal

import pytest
from fastapi import HTTPException
from sqlalchemy import select

from app.database import SessionLocal, init_db
from app.models import (
    AuditLog,
    BatchRun,
    Case,
    Diagnosis,
    Message,
    PolicyDecision,
)
from app.pipeline import run_batch
from app.services.audit_service import EVENT_ESCALATE, EVENT_BATCH_SUMMARY


def _make_cases(n: int = 20) -> list[str]:
    db = SessionLocal()
    try:
        ids = []
        for i in range(n):
            case = Case(
                id=f"ai{i:04d}",
                subscription_id=f"sub_ai_{i}",
                merchant_id="m_ai",
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
    finally:
        db.close()


@pytest.fixture(scope="module")
def ai_batch():
    init_db()
    case_ids = _make_cases(20)
    db = SessionLocal()
    try:
        batch = run_batch(db, 20)
        return batch.id, case_ids
    finally:
        db.close()


def test_ai_usage_counts_sum_to_cases(ai_batch):
    batch_id, case_ids = ai_batch
    db = SessionLocal()
    try:
        from app.routes import get_batch_ai_usage
        from fastapi import HTTPException
        response = get_batch_ai_usage(batch_id, db)
        total_diags = response.diagnoses_by_rule + response.diagnoses_by_llm
        assert total_diags == len(case_ids)

        diags = db.execute(
            select(Diagnosis).where(Diagnosis.case_id.in_(case_ids))
        ).scalars().all()
        rule_count = sum(1 for d in diags if d.source == "rule")
        llm_count = sum(1 for d in diags if d.source in ("llm", "mock"))
        assert response.diagnoses_by_rule == rule_count
        assert response.diagnoses_by_llm == llm_count

        esc = db.execute(
            select(AuditLog).where(
                AuditLog.case_id.in_(case_ids),
                AuditLog.event_type == EVENT_ESCALATE,
            )
        ).scalars().all()
        assert response.escalations_from_low_confidence == len(esc)

        msgs = db.execute(
            select(Message).where(Message.case_id.in_(case_ids))
        ).scalars().all()
        assert response.messages_drafted_by_llm == len(msgs)

        assert response.money_decisions_made_by_ai == 0
    finally:
        db.close()


def test_ai_usage_404_on_missing_batch():
    db = SessionLocal()
    try:
        from app.routes import get_batch_ai_usage
        with pytest.raises(HTTPException) as exc:
            get_batch_ai_usage("does-not-exist", db)
        assert exc.value.status_code == 404
    finally:
        db.close()
