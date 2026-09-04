"""SQLAlchemy ORM models for RENEW.

Design notes:
- Idempotency: `AuditLog` carries a unique constraint on
  (case_id, event_type); re-running the pipeline on the same case cannot
  produce duplicate lifecycle audit events. This satisfies the "idempotency
  via DB unique constraint" constraint without any distributed lock.
- Ground truth fields (`true_recoverable`,
  `true_would_recover_without_action`) exist ONLY for evaluation /
  simulation / baseline comparison. They must never be passed to the scorer
  as features nor read by the policy engine.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Enum,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.database import Base

FAILURE_CLASSES = (
    "expired_card",
    "insufficient_funds",
    "bank_decline",
    "mandate_cancelled",
    "unknown",
)

INTERVENTIONS = (
    "retry_now",
    "retry_after_cooldown",
    "send_message",
    "escalate",
    "stop",
)

CASE_STATUSES = (
    "new",
    "diagnosed",
    "scored",
    "intervened",
    "resolved",
    "stopped",
)

DIAGNOSIS_SOURCES = ("rule", "llm", "mock")

# Interventions that count as a recovery *attempt* for metrics purposes.
RECOVERY_INTERVENTIONS = ("retry_now", "retry_after_cooldown", "send_message")


def _uuid() -> str:
    return uuid.uuid4().hex


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


class Case(Base):
    __tablename__ = "cases"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    subscription_id: Mapped[str] = mapped_column(String(64), index=True)
    merchant_id: Mapped[str] = mapped_column(String(64), index=True)
    amount: Mapped[Decimal] = mapped_column(Numeric(12, 2))
    currency: Mapped[str] = mapped_column(String(8), default="INR")
    failure_code: Mapped[str | None] = mapped_column(String(64), nullable=True)
    failure_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    customer_tenure_months: Mapped[int] = mapped_column(Integer)
    prior_failure_count: Mapped[int] = mapped_column(Integer)
    payment_method: Mapped[str] = mapped_column(String(32))
    merchant_category: Mapped[str] = mapped_column(String(32))
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    status: Mapped[str] = mapped_column(
        Enum(*CASE_STATUSES, name="case_status", native_enum=False),
        default="new",
        index=True,
    )
    # --- hidden synthetic ground truth (never exposed to scorer/policy) ---
    true_recoverable: Mapped[bool] = mapped_column(Boolean, default=False)
    true_would_recover_without_action: Mapped[bool] = mapped_column(Boolean, default=False)
    # --- generation marker (never exposed to scorer/policy; used by the
    #     failure-story rerun to guarantee minimum segment representation) ---
    is_failure_segment: Mapped[bool] = mapped_column(Boolean, default=False, index=True)


class Diagnosis(Base):
    __tablename__ = "diagnoses"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    failure_class: Mapped[str] = mapped_column(
        Enum(*FAILURE_CLASSES, name="failure_class", native_enum=False)
    )
    confidence: Mapped[float] = mapped_column(Float)
    source: Mapped[str] = mapped_column(
        Enum(*DIAGNOSIS_SOURCES, name="diagnosis_source", native_enum=False)
    )
    rationale: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Score(Base):
    __tablename__ = "scores"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    recoverability: Mapped[float] = mapped_column(Float)
    model_version: Mapped[str] = mapped_column(String(32))
    top_features: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class PolicyDecision(Base):
    __tablename__ = "policy_decisions"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    intervention: Mapped[str] = mapped_column(
        Enum(*INTERVENTIONS, name="intervention", native_enum=False), index=True
    )
    reason: Mapped[str] = mapped_column(Text)  # mandatory, human-readable
    budget_consumed: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class Message(Base):
    __tablename__ = "messages"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    case_id: Mapped[str] = mapped_column(ForeignKey("cases.id"), index=True)
    channel: Mapped[str] = mapped_column(String(32), default="email")
    body: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class AuditLog(Base):
    """Append-only audit trail.

    No API route may UPDATE or DELETE rows here; the pipeline only INSERTs.
    The unique constraint on (case_id, event_type) makes per-case lifecycle
    events idempotent at the database level.
    """

    __tablename__ = "audit_logs"
    __table_args__ = (
        UniqueConstraint("case_id", "event_type", name="uq_audit_case_event"),
    )

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    case_id: Mapped[str | None] = mapped_column(
        ForeignKey("cases.id"), nullable=True, index=True
    )  # nullable for batch-level events
    event_type: Mapped[str] = mapped_column(String(64), index=True)
    payload: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)


class BatchRun(Base):
    __tablename__ = "batch_runs"

    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=_uuid)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=_utcnow)
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    total_cases: Mapped[int] = mapped_column(Integer, default=0)
    total_at_risk_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    total_recovered_amount: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    total_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    net_recovered: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    recovery_rate: Mapped[float] = mapped_column(Float, default=0.0)
    baseline_recovery_rate: Mapped[float] = mapped_column(Float, default=0.0)
    false_positive_cost: Mapped[Decimal] = mapped_column(Numeric(14, 2), default=0)
    cases_blocked_by_stopping_rules: Mapped[int] = mapped_column(Integer, default=0)
    # Pool-topup accounting (Step 1 fix): requested N, auto-topup count.
    requested_cases: Mapped[int | None] = mapped_column(Integer, nullable=True)
    cases_topped_up: Mapped[int | None] = mapped_column(Integer, nullable=True)

