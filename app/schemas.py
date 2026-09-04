"""Pydantic v2 request/response schemas."""

from __future__ import annotations

from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, Field


class BatchRunRequest(BaseModel):
    n_cases: int = Field(default=100, ge=1, le=600)
    # None -> original policy; 0.85 -> documented fix (spec §17)
    segment_send_threshold: float | None = Field(default=None, ge=0.0, le=1.0)


class BatchRunResponse(BaseModel):
    id: str
    started_at: datetime
    finished_at: datetime | None
    total_cases: int
    total_at_risk_amount: Decimal
    total_recovered_amount: Decimal
    total_cost: Decimal
    net_recovered: Decimal
    recovery_rate: float
    baseline_recovery_rate: float
    false_positive_cost: Decimal
    cases_blocked_by_stopping_rules: int
    # Pool-topup accounting (Step 1 fix): requested N, actually-processed
    # M, and how many synthetic cases were auto-generated to top the pool up.
    requested_cases: int | None = None
    cases_topped_up: int | None = None


class AuditEntry(BaseModel):
    event_type: str
    payload: dict
    created_at: datetime


class CaseDetailResponse(BaseModel):
    id: str
    subscription_id: str
    merchant_id: str
    amount: Decimal
    currency: str
    failure_code: str | None
    failure_message: str | None
    customer_tenure_months: int
    prior_failure_count: int
    payment_method: str
    merchant_category: str
    status: str
    created_at: datetime
    diagnosis: dict | None = None
    score: dict | None = None
    policy_decision: dict | None = None
    message: str | None = None
    audit_trail: list[AuditEntry] = []


class CaseSummary(BaseModel):
    id: str
    subscription_id: str
    amount: Decimal
    status: str
    prior_failure_count: int
    created_at: datetime
    failure_class: str | None = None  # populated from Diagnosis, may be None


class SegmentRow(BaseModel):
    segment: str
    cases: int
    recovered_cases: int
    recovered_amount: float
    cost: float
    net_recovered: float
    recovery_rate: float


class AIUsageResponse(BaseModel):
    diagnoses_by_rule: int
    diagnoses_by_llm: int
    escalations_from_low_confidence: int
    messages_drafted_by_llm: int
    money_decisions_made_by_ai: int = 0


class SandboxRequest(BaseModel):
    segment_send_threshold: float | None = Field(default=0.85, ge=0.5, le=1.0)
    budget_cap: float = Field(default=5000.0, ge=0, le=20000)
    message_estimated_cost: float = Field(default=300.0, ge=50, le=1000)
    sample_size: int = Field(default=300, ge=50, le=600)


class SandboxResponse(BaseModel):
    total_cases: int
    total_at_risk_amount: float
    total_recovered_amount: float
    total_cost: float
    net_recovered: float
    recovery_rate: float
    baseline_recovery_rate: float
    false_positive_cost: float
    cases_blocked_by_stopping_rules: int
    is_simulation: bool = True
    sample_size_used: int


class FailureStoryResponse(BaseModel):
    before: dict
    after: dict
    narrative: dict
    # When populated, the latest numbers from POST /failure-story/rerun.
    # The canonical numbers in `before`/`after`/`narrative` never change
    # after seed; only `latest` is updated by rerun.
    latest: dict | None = None
