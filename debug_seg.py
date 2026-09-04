"""Diagnose segment scores across recent batches."""
from app.database import SessionLocal
from app.models import Case, BatchRun, PolicyDecision, Score, AuditLog
from sqlalchemy import select, func

db = SessionLocal()
batches = list(db.execute(select(BatchRun).order_by(BatchRun.started_at.desc()).limit(20)).scalars())
for b in batches:
    if b.total_cases != 300:
        continue
    ev = next((e for e in db.execute(select(AuditLog).where(AuditLog.event_type == 'batch_summary')).scalars()
               if (e.payload or {}).get('batch_run_id') == b.id), None)
    if not ev:
        continue
    case_ids = list(ev.payload.get('case_ids', []))
    cases = db.execute(select(Case).where(Case.id.in_(case_ids))).scalars().all()
    seg_cases = [c for c in cases if c.is_failure_segment]
    scores_by_case = {s.case_id: s for s in db.execute(select(Score).where(Score.case_id.in_(case_ids))).scalars()}
    decisions_by_case = {d.case_id: d for d in db.execute(select(PolicyDecision).where(PolicyDecision.case_id.in_(case_ids))).scalars()}
    msgs = [c for c in seg_cases if decisions_by_case.get(c.id) and decisions_by_case[c.id].intervention == 'send_message']
    escalates = [c for c in seg_cases if decisions_by_case.get(c.id) and decisions_by_case[c.id].intervention == 'escalate']
    stops = [c for c in seg_cases if decisions_by_case.get(c.id) and decisions_by_case[c.id].intervention == 'stop']
    print(f"batch {b.id[:8]} started={b.started_at} seg={len(seg_cases)} msg={len(msgs)} esc={len(escalates)} stop={len(stops)}")
    if seg_cases:
        sc_list = [scores_by_case[c.id].recoverability for c in seg_cases if c.id in scores_by_case]
        if sc_list:
            print(f"  segment scores: min={min(sc_list):.3f} max={max(sc_list):.3f} avg={sum(sc_list)/len(sc_list):.3f}")
    if msgs:
        for c in msgs[:3]:
            print(f"  msg: case={c.id} score={scores_by_case.get(c.id) and scores_by_case[c.id].recoverability:.3f} amount={c.amount} pfc={c.prior_failure_count}")
