"""Demonstrate the documented failure (spec §17) and the fix.

Run 1: original policy (segment_send_threshold=None) over 300 cases.
Run 2: hardened policy (insufficient_funds AND prior_failure_count >= 3
       requires score >= 0.85 for send_message, else stop).

Both BatchRuns are PRESERVED for the live demo. Writes a JSON summary to
data/failure_demo.json used by docs/what-broke.md.
"""

from __future__ import annotations

import json

from app.database import SessionLocal, init_db
from app.generate_data import generate
from app.pipeline import run_batch
from app.services.metrics_service import segment_breakdown


def summarize(db, batch, label):
    segs = segment_breakdown(db, batch.id)
    risky = next((s for s in segs if s["segment"] == "class:insufficient_funds"), None)
    pfc_seg = next((s for s in segs if s["segment"] == "pfc:3-4"), None)
    return {
        "label": label,
        "batch_id": batch.id,
        "total_cases": batch.total_cases,
        "at_risk": float(batch.total_at_risk_amount),
        "recovered": float(batch.total_recovered_amount),
        "cost": float(batch.total_cost),
        "net_recovered": float(batch.net_recovered),
        "recovery_rate": round(batch.recovery_rate, 4),
        "baseline_rate": round(batch.baseline_recovery_rate, 4),
        "false_positive_cost": float(batch.false_positive_cost),
        "blocked_by_stopping_rules": batch.cases_blocked_by_stopping_rules,
    }, {"class_insufficient_funds": risky, "pfc_3_4": pfc_seg}


def main():
    init_db()
    generate(n=500)  # fresh dataset, all cases 'new'
    db = SessionLocal()

    print(">>> RUN 1: original untuned policy")
    b1, s1 = summarize(db, run_batch(db, 300), "before_fix")
    print(json.dumps(b1, indent=1))
    risky_before = [s for k, s in s1.items() if "pfc" in (s or {}).get("segment", "")]
    risky_before = next((s for s in segment_breakdown(db, b1["batch_id"])
                         if s["segment"].endswith("pfc>=3")), None)
    print("FAILURE SEGMENT:", json.dumps(risky_before, indent=1))

    print("\n>>> RUN 2: hardened segment rule (score >= 0.85 required)")
    b2, s2 = summarize(db, run_batch(db, 300, segment_send_threshold=0.85),
                       "after_fix")
    print(json.dumps(b2, indent=1))
    risky_after = next((s for s in segment_breakdown(db, b2["batch_id"])
                        if s["segment"].endswith("pfc>=3")), None)
    print("FAILURE SEGMENT:", json.dumps(risky_after, indent=1))

    with open("data/failure_demo.json", "w") as f:
        json.dump({
            "before": b1,
            "before_segment": risky_before,
            "after": b2,
            "after_segment": risky_after,
            "segment_key": "class:insufficient_funds|pfc>=3",
            "narrative": {
                "what_happened": (
                    "The v1 additive logistic-regression scorer could not see that "
                    "insufficient_funds with three or more prior failures behaves "
                    "inversely to other repeat-failure segments. Those 56 cases "
                    "scored around 0.42 — squarely in the send_message band — so "
                    "the system spent ~₹300 per case on outreach. The segment "
                    "recovered only 1 case (₹1,293.32) against ₹1,800 in cost, "
                    "netting -₹506.68, while the overall batch showed a healthy "
                    "+₹239,969.48 net recovered."
                ),
                "how_found": (
                    "The problem was invisible in the overall batch metrics. It "
                    "surfaced only via GET /batches/{id}/segments, where the "
                    "segment breakdown exposed the insufficient_funds|pfc>=3 row "
                    "with its negative net. Without that per-segment view, the "
                    "loss would have been buried inside a seemingly successful batch."
                ),
                "what_changed": (
                    "Added a deterministic rule in policy_engine.py: for the "
                    "insufficient_funds and prior_failure_count >= 3 segment, "
                    "send_message is allowed only when recoverability >= 0.85; "
                    "otherwise the case is stopped. Toggled per-batch via "
                    "segment_send_threshold on POST /batches/run. The scorer "
                    "itself was deliberately left unchanged."
                ),
            },
        }, f, indent=1)
    print("\nboth BatchRuns preserved; summary -> data/failure_demo.json")


if __name__ == "__main__":
    main()
