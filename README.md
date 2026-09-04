# RENEW — Failed Subscription Revenue Recovery

> **Diagnose before you act** — turn failed subscription payments into
> measured, audited, bounded recovery, not blind retries.

RENEW processes failed recurring payments through a controlled pipeline:

```
Failed payment → Diagnosis → Recoverability score → Deterministic policy
→ Simulated intervention → Append-only audit → Batch metrics & segments
```

The LLM is used in **exactly two places** — classifying ambiguous free-text
failure reasons into a fixed enum, and drafting customer message wording.
Every money-affecting decision (retry / cooldown / message / escalate /
stop, and every rupee of budget) is made by a pure, deterministic,
unit-tested rules module.

## Quick start

**Primary path — one click, works on a fresh clone:**

1. `python3.11 -m venv .venv && source .venv/bin/activate && pip install -r requirements.txt`
2. `uvicorn app.main:app --port 8010 --reload`
3. `cd frontend && npm install && npm run dev` → open http://localhost:5173
4. The **About** screen is shown first. If the database is empty, click the
   single **"Set up demo data"** button — it calls `POST /admin/seed`, which
   generates 500 synthetic cases, trains the scorer, and runs both before/after
   batches server-side. No manual scripts needed.

**Fallback — manual scripts (if you prefer the CLI):**

```bash
python -m app.generate_data --n 500     # synthetic data
python -m app.train_scorer              # trains models/scorer.pkl + docs/eval-report.md
PYTHONPATH=. python scripts/failure_demo.py   # before/after failure story batches
```

The `POST /admin/seed` endpoint is idempotent: it returns
`{"status": "already_seeded"}` if cases already exist. Pass
`?force=true` to wipe and regenerate.

Docker convenience: `docker compose up --build` (backend + frontend only;
there is deliberately no PostgreSQL/Redis container).

Run tests:

```bash
pytest            # policy rules, budget invariants, cooldowns, golden metrics, integration
```

Reproduce the documented-failure demo:

```bash
PYTHONPATH=. python scripts/failure_demo.py    # runs before-fix and after-fix batches
```

## Architecture

| Module | Responsibility | Purity |
|---|---|---|
| `app/services/diagnosis_service.py` | structured-code lookup (rule) or LLM classification of free text | rule path pure; LLM path validated |
| `app/scorer.py` / `train_scorer.py` | tabular ML recoverability probability | read-only model |
| `app/services/policy_engine.py` | **THE decision module** — all interventions & budget spend | pure, deterministic, no I/O |
| `app/services/message_service.py` | LLM drafts wording AFTER `send_message` was chosen | never chooses actions |
| `app/services/audit_service.py` | append-only audit trail (INSERT only) | no update/delete anywhere |
| `app/services/metrics_service.py` | batch KPIs + per-segment breakdown | reads stored rows |
| `app/pipeline.py` | one function = one case end-to-end; batch runner | orchestration |

### Key design decisions

**1. Why a tabular ML model instead of an LLM for scoring.**
The dataset is small (~500 rows), fully tabular, with a binary target.
A scikit-learn pipeline gives: calibrated probabilities (an LLM gives vibes),
sub-millisecond inference for hundreds of cases, a leakage-free
train/val/test protocol with real precision/recall/F1/AUC numbers
(`docs/eval-report.md`), reproducibility (fixed seed), per-feature
importance, and zero marginal cost per case. An LLM cannot be evaluated this
honestly at this data size, is slower, costlier, and non-deterministic —
unacceptable for a component whose output feeds money decisions.

<!-- PART2 -->

**2. Why the LLM can never make money-affecting decisions.**
LLM output is probabilistic; money decisions must be auditable and
reproducible. RENEW's split of labour:

- the LLM classifies ambiguous free text into a fixed enum (validated against
  a strict schema, one stricter retry, deterministic `unknown` fallback); and
  drafts message wording after an intervention was already chosen;
- the policy engine — pure Python rules with first-match-wins ordering —
  chooses every intervention, consumes budget, and enforces stopping rules.

An LLM therefore cannot invent an amount, pick a retry, decide escalation,
stop recovery, or spend budget: it has no code path to do so. Every decision
row stores a human-readable `reason` produced by the rule that fired.

**3. Deterministic core.**
`policy_engine.py` is pure (no DB, no network, time injected), so all seven
rule branches, cooldown behaviour, mandate-cancellation stops, and the
budget invariant are proven by unit tests — including a simulated
500-random-case batch asserting the cap is never exceeded.

**4. Safety stop / graceful degradation.**
Diagnosis confidence below 0.5 flags the case for human review; it is never
auto-scored or auto-intervened. The system degrades to "ask a human" instead
of guessing.

**5. SQLite + unique-constraint idempotency (no distributed lock).**
One process, one file. Lifecycle audit events carry a UNIQUE constraint on
`(case_id, event_type)`, making re-processing idempotent at the storage layer.
A distributed lock would add operational complexity this single-node system
cannot justify.

**6. No Alembic.**
Schema churn is handled by regenerating the synthetic dataset; migrations
would be ceremony without value here.

**7. Append-only auditing.**
Audit rows are INSERT-only; there are no update/delete functions or routes.
The case explorer renders diagnosis → score → policy decision → message →
outcome chronologically, including each decision's reason.

## The documented failure

The v1 scorer deliberately shipped untuned (additive logistic regression).
It could not see that `insufficient_funds ∧ prior_failure_count ≥ 3` behaves
inversely to other repeat-failure segments — so it scored those hopeless,
small-ticket cases ~0.42, the policy messaged them, and **the segment lost
₹506.68 while the overall batch showed +₹239,969 net recovered.**
Discovered via `GET /batches/{id}/segments`, fixed with a bounded
deterministic rule (segment requires score ≥ 0.85 for outreach).

Full before/after numbers: **[docs/what-broke.md](docs/what-broke.md)**.
Both BatchRun records are preserved in the demo database.

## Evaluation results

Held-out test split (`docs/eval-report.md`): precision 0.79 · recall 0.71 ·
F1 0.75 · ROC-AUC 0.77 · calibration table included. The scorer never sees
ground-truth fields — enforced by raising on forbidden feature names.

## API

| Method | Path | Purpose |
|---|---|---|
| GET | `/health` | liveness + DB check |
| POST | `/batches/run` | run pipeline over N unprocessed cases |
| GET | `/batches` | all batch runs, newest first |
| GET | `/batches/latest` | most recent batch run |
| GET | `/batches/{id}` | batch summary |
| GET | `/batches/{id}/segments` | per-class & per-prior-failure metrics |
| GET | `/batches/{id}/ai-usage` | AI vs rule diagnosis counts, message drafts, money decisions |
| POST | `/sandbox/simulate` | side-effect-free policy replay with custom thresholds |
| GET | `/failure-story` | before/after failure story with narrative |
| POST | `/failure-story/rerun` | regenerate the failure story on fresh cases |
| GET | `/cases/{id}` | full case detail + chronological audit trail |
| GET | `/cases?status=&failure_class=` | filtered case list |

No PUT/DELETE routes exist for audit history or case history. Payment
execution is simulated; no real keys or gateway calls anywhere.

## LLM providers

Set `RENEW_LLM_PROVIDER=anthropic` (+ `ANTHROPIC_API_KEY`) or `openai`
(+ `OPENAI_API_KEY`, optionally `RENEW_LLM_MODEL`). Default `mock` runs fully
offline with deterministic keyword classification and template copy — clearly
labelled in outputs so demo results are honest about AI involvement.

## What's new

**Failure Story screen** — the before/after documented failure is now visible
in the product as the first screen. `GET /failure-story` reads live DB state
plus a narrative object from `data/failure_demo.json`; `POST
/failure-story/rerun` regenerates both batch runs on fresh cases.

**AI Judgment scoreboard** — `GET /batches/{id}/ai-usage` exposes how many
diagnoses used rules vs LLM, how many messages were drafted, and explicitly
shows `money_decisions_made_by_ai = 0` because `policy_engine.decide()` never
calls a model. The Dashboard renders this as a compact strip; Case Explorer
shows a source badge on each diagnosis and a lock icon on every policy
decision.

**Live Policy Sandbox** — `POST /sandbox/simulate` re-runs the production
`policy_engine.decide()` in memory against already-diagnosed cases with
judge-adjustable thresholds. It returns computed metrics without writing a
single row. The frontend provides sliders for segment threshold, budget cap,
and message cost, with a 300ms debounce and a persistent "SIMULATED" tag.

