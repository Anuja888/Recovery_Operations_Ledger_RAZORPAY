"""Smoke-test: run a small batch end-to-end and inspect results."""
import json

from app.database import SessionLocal, init_db
from app.models import AuditLog, Case
from app.pipeline import run_batch

init_db()
db = SessionLocal()
batch = run_batch(db, 20)
print("=== BATCH ===")
for k in ("id", "total_cases", "total_at_risk_amount", "total_recovered_amount",
          "total_cost", "net_recovered", "recovery_rate",
          "baseline_recovery_rate", "false_positive_cost",
          "cases_blocked_by_stopping_rules"):
    print(f"  {k}: {getattr(batch, k)}")

trails = db.query(AuditLog).filter(AuditLog.case_id.in_(
    db.query(Case.id).filter(Case.status != "new"))).all()
per_case = {}
for e in trails:
    if e.case_id:
        per_case.setdefault(e.case_id, []).append(e.event_type)
print(f"\ncases with audit trail: {len(per_case)}, events total: {len(trails)}")
sample = next(iter(per_case.items()))
print("sample trail:", sample[1])

from collections import Counter

status_counts = Counter(s for (s,) in db.query(Case.status).all())
print("status counts:", dict(status_counts))
