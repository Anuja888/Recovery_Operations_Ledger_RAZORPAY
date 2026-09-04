"""Central configuration for RENEW.

All tunable thresholds live here so policy/safety behaviour is explicit and
auditable rather than buried in code.
"""

from __future__ import annotations

import os
from dataclasses import dataclass, field


def _env_float(name: str, default: float) -> float:
    try:
        return float(os.environ.get(name, default))
    except ValueError:
        return default


@dataclass
class Settings:
    # --- diagnosis safety ---
    # Below this confidence a case is flagged for human review instead of
    # being automatically scored/intervened (graceful degradation).
    low_confidence_threshold: float = _env_float("RENEW_LOW_CONFIDENCE", 0.5)

    # --- LLM (used ONLY for ambiguous diagnosis + message wording) ---
    llm_provider: str = os.environ.get("RENEW_LLM_PROVIDER", "mock")  # anthropic|openai|mock
    llm_model: str = os.environ.get("RENEW_LLM_MODEL", "")
    anthropic_api_key: str = field(default_factory=lambda: os.environ.get("ANTHROPIC_API_KEY", ""))
    openai_api_key: str = field(default_factory=lambda: os.environ.get("OPENAI_API_KEY", ""))

    # --- batch budget (hard cap on escalation spending per batch) ---
    batch_budget_cap: float = _env_float("RENEW_BATCH_BUDGET_CAP", 5000.0)

    # --- message cost model (simulated) ---
    # A personalized recovery outreach (email + SMS + support follow-up)
    # costs real money; set high enough that spraying messages at hopeless
    # cases visibly destroys net recovered -- the documented failure.
    message_estimated_cost: float = _env_float("RENEW_MESSAGE_COST", 300.0)


settings = Settings()
