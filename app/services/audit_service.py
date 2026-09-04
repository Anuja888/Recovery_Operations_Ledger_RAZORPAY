"""Append-only audit service.

Writes are INSERT-only. There are intentionally NO update/delete functions
here and no API routes mutate AuditLog (see app/routes). The unique
constraint on (case_id, event_type) makes lifecycle events idempotent:
re-processing a case cannot duplicate its audit history.
"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models import AuditLog

EVENT_DIAGNOSIS = "diagnosis"
EVENT_SCORE = "score"
EVENT_POLICY_DECISION = "policy_decision"
EVENT_MESSAGE = "customer_message"
EVENT_RETRY = "intervention_retry"
EVENT_ESCALATE = "escalation"
EVENT_BATCH_SUMMARY = "batch_summary"


def log_event(db: Session, event_type: str, payload: dict,
              case_id: str | None = None) -> AuditLog:
    entry = AuditLog(case_id=case_id, event_type=event_type, payload=payload)
    db.add(entry)
    db.flush()
    return entry


def get_case_trail(db: Session, case_id: str) -> list[AuditLog]:
    """Chronological audit trail for one case."""
    return list(
        db.execute(
            select(AuditLog)
            .where(AuditLog.case_id == case_id)
            .order_by(AuditLog.created_at.asc())
        ).scalars()
    )


def get_recent_retry_event(db: Session, case_id: str, since) -> AuditLog | None:
    """Most recent retry event for a case within `since` (cooldown check)."""
    return db.execute(
        select(AuditLog)
        .where(
            AuditLog.case_id == case_id,
            AuditLog.event_type == EVENT_RETRY,
            AuditLog.created_at >= since,
        )
        .order_by(AuditLog.created_at.desc())
        .limit(1)
    ).scalar_one_or_none()
