# RENEW — Failed Subscription Revenue Recovery System

## Build Specification

Build **RENEW**, a failed-subscription revenue recovery system for a hackathon submission.

The project should demonstrate that:

- the application runs reliably;
- the codebase is structured and understandable;
- the system can be trusted because important decisions are controlled and auditable;
- AI is used only where it is justified;
- failures and limitations are honestly documented.

This document preserves the original product idea, scope, rules, and features. It only presents them in a clearer and more structured form.

---

# 1. Core Idea

Subscription businesses lose revenue when recurring payments fail because of reasons such as:

- expired cards;
- insufficient funds;
- bank declines;
- cancelled mandates.

A simple retry-everything strategy is inefficient, while doing nothing leaves recoverable revenue behind.

**RENEW** processes each failed subscription payment through a controlled recovery pipeline:

1. Diagnose the payment failure.
2. Estimate how recoverable the case is.
3. Use a deterministic policy engine to select one bounded action.
4. Simulate execution.
5. Record every important step in an audit trail.
6. Measure recovered revenue, cost, and recovery performance.

The available interventions are:

- retry immediately;
- retry after a cooldown;
- send a recovery message;
- escalate for human review;
- stop.

All money-affecting decisions remain deterministic and rule-based.

### One-line pitch

> **Diagnose before you act — turn failed subscription payments into measured, audited, bounded recovery, not blind retries.**

---

# 2. Hard Constraints

The following constraints must not be violated.

## Architecture and infrastructure

Do not use:

- multi-agent frameworks;
- LangChain or LangGraph;
- vector databases;
- Kubernetes;
- Docker Swarm;
- fine-tuning;
- blockchain.

## Payments and data

- Never use real Razorpay keys.
- Use synthetic data only.
- Payment execution must be simulated.

## LLM usage

The LLM is allowed in exactly two places:

1. Classifying ambiguous free-text payment failure reasons into a fixed failure enum.
2. Drafting customer-facing message copy after an intervention has already been selected.

The LLM must never:

- choose an intervention;
- generate a monetary amount;
- decide whether to escalate;
- decide whether to stop;
- control budget consumption.

## Deterministic money decisions

All money-affecting decisions must live in:

`policy_engine.py`

This module must:

- be pure;
- have no external calls;
- be deterministic;
- be unit-testable.

## Database

- Use SQLite through SQLAlchemy.
- Do not use PostgreSQL.
- Do not use Redis.
- Enforce idempotency with a database unique constraint.
- Do not use a distributed lock.

## Repository and documentation

Use:

- one repository;
- one main `README.md`.

The README must explain each major architecture decision in plain language and defend why that choice was made instead of more complex alternatives.

---

# 3. Technology Stack

## Backend

- Python 3.11
- FastAPI
- SQLAlchemy 2.0
- SQLite
- Pydantic v2

## Recoverability scoring

Use either:

- scikit-learn; or
- LightGBM.

The dataset is small and tabular, so the README must explain why a traditional ML model is more appropriate than an LLM for this prediction task.

## LLM

Use one API-based model, such as a Claude-class or GPT-4o-class model.

The LLM must use strict structured output validation for:

- diagnosis fallback;
- customer message generation.

## Frontend

- React
- Vite
- TypeScript
- Tailwind CSS

## Testing

Use `pytest`, with particular focus on `policy_engine.py`.

## Docker

Docker is not required for normal development, but include a `docker-compose.yml` for convenience.

It must contain only:

- backend;
- frontend.

Do not add PostgreSQL or Redis containers.

---

# 4. System Flow

Each failed subscription payment should follow this flow:

```text
Failed Payment
      ↓
Diagnosis
      ↓
Recoverability Score
      ↓
Deterministic Policy Decision
      ↓
Simulated Intervention
      ↓
Audit Logging
      ↓
Outcome and Batch Metrics
```

The system must keep the decision process separated into clear responsibilities:

- diagnosis identifies the failure class;
- scoring estimates recoverability;
- policy selects the allowed action;
- the LLM may only assist with ambiguous diagnosis or message wording;
- auditing records what happened;
- metrics evaluate the batch.

---

# 5. Data Model

Use SQLAlchemy models.

## Case

```text
id (uuid, pk)
subscription_id (str)
merchant_id (str)
amount (decimal)
currency (str, default "INR")
failure_code (str, nullable)
failure_message (str, nullable)
customer_tenure_months (int)
prior_failure_count (int)
payment_method (str)
merchant_category (str)
created_at (datetime)
status (
  new,
  diagnosed,
  scored,
  intervened,
  resolved,
  stopped
)
true_recoverable (bool)
true_would_recover_without_action (bool)
```

The last two fields are synthetic ground truth fields.

They must:

- be generated for evaluation;
- never be exposed to the scorer;
- never be used by the policy engine.

## Diagnosis

```text
id (pk)
case_id (fk)
failure_class (
  expired_card,
  insufficient_funds,
  bank_decline,
  mandate_cancelled,
  unknown
)
confidence (float)
source (
  rule,
  llm
)
rationale (text)
created_at
```

## Score

```text
id (pk)
case_id (fk)
recoverability (float, 0-1)
model_version (str)
top_features (json)
created_at
```

## PolicyDecision

```text
id (pk)
case_id (fk)
intervention (
  retry_now,
  retry_after_cooldown,
  send_message,
  escalate,
  stop
)
reason (text)
budget_consumed (decimal, nullable)
created_at
```

The `reason` field is mandatory and must clearly explain why the policy engine selected the action.

## Message

```text
id (pk)
case_id (fk)
channel (str)
body (text)
created_at
```

## AuditLog

```text
id (pk)
case_id (fk, nullable for batch-level events)
event_type (str)
payload (json)
created_at
```

Audit logs must be append-only.

There must be no API endpoints that update or delete audit records.

## BatchRun

```text
id (pk)
started_at
finished_at
total_cases (int)
total_at_risk_amount (decimal)
total_recovered_amount (decimal)
total_cost (decimal)
net_recovered (decimal)
recovery_rate (float)
baseline_recovery_rate (float)
false_positive_cost (decimal)
cases_blocked_by_stopping_rules (int)
```

---

# 6. Synthetic Data Generation

Create:

`generate_data.py`

Generate between **400 and 600** `Case` rows.

## Failure information distribution

Approximately:

- 70% of cases should contain a structured `failure_code`;
- the remaining approximately 30% should use a free-text `failure_message`.

Structured failure codes must map deterministically to a failure class.

Free-text messages require diagnosis through the fallback process.

## Failure class distribution

Make these more common:

- insufficient_funds;
- bank_decline.

Make these less common:

- mandate_cancelled;
- expired_card.

## Hidden ground truth

Generate:

- `true_recoverable`;
- `true_would_recover_without_action`.

Both must come from a hidden synthetic function based on the case features, with some noise.

These fields are used only for:

- evaluation;
- simulation;
- baseline comparison.

They must not be available to the scorer or policy engine.

## Deliberate failure segment

Intentionally create a difficult segment:

```text
failure_class = insufficient_funds
AND
prior_failure_count >= 3
```

For this group:

- the true recoverability should be disproportionately low;
- feature values should still make an untuned model consider many cases moderately recoverable.

For example, long customer tenure can normally correlate with recoverability and can make this segment appear better than it actually is.

The expected result is that the first version of the system may over-retry or over-message this segment.

This must later become the documented failure.

Do not fix this behavior before demonstrating it with real batch metrics.

## Dataset split

Split data by `case_id`:

- 70% training;
- 15% validation;
- 15% testing.

Prevent leakage between splits.

---

# 7. Diagnosis Service

Create:

`diagnosis_service.py`

## Structured failure code

If `failure_code` exists:

- use a deterministic dictionary lookup;
- assign the corresponding `failure_class`;
- set `confidence = 1.0`;
- set `source = "rule"`.

## Free-text failure message

If only `failure_message` exists, use the LLM.

The LLM must classify the message into exactly one of:

```text
expired_card
insufficient_funds
bank_decline
mandate_cancelled
unknown
```

Expected structured response:

```json
{
  "failure_class": "...",
  "confidence": 0.0,
  "rationale": "..."
}
```

Validate the response against a strict JSON schema.

If validation fails:

1. retry once with a stricter instruction;
2. if the second attempt also fails, fall back to:

```text
failure_class = unknown
confidence = 0
source = rule
```

## Low-confidence safety stop

Define a configurable confidence threshold at the top of the file.

Default:

```text
0.5
```

If confidence is below `0.5`:

- mark the case as `diagnosed`;
- flag it as needing review;
- do not allow automatic scoring or intervention.

This is an intentional safety mechanism and must be explained in the README as graceful degradation.

---

# 8. Recoverability Scorer

Create:

- `train_scorer.py`
- `scorer.py`

## Training

Train a classifier using:

```text
failure_class
amount
customer_tenure_months
prior_failure_count
payment_method
merchant_category
```

The prediction target is:

```text
true_recoverable
```

Save the trained model to:

```text
models/scorer.pkl
```

## Evaluation

Evaluate on the held-out test split.

Report:

- precision;
- recall;
- F1;
- AUC.

Also perform a calibration check comparing:

```text
predicted probability bucket
vs
actual recovery rate
```

Save the results to:

```text
docs/eval-report.md
```

The report must contain real evaluation numbers.

## Runtime scoring

`scorer.py` should expose:

```python
score(case_features) -> float
```

It should also provide the most important contributing features using:

- feature importance; or
- SHAP, if time allows.

---

# 9. Deterministic Policy Engine

Create:

`policy_engine.py`

This is the core decision module.

It must be:

- pure;
- deterministic;
- free of I/O;
- free of external API calls;
- fully unit-testable.

Given:

```text
diagnosis
score
case
BatchBudget
```

it returns one `PolicyDecision`.

## Rule order

Rules are evaluated in order.

**First matching rule wins.**

### Rule 1 — Low diagnosis confidence

If:

```text
diagnosis.confidence < 0.5
```

then:

```text
intervention = escalate
reason = "low diagnosis confidence, human review required"
```

### Rule 2 — Repeated mandate cancellation

If:

```text
case.prior_failure_count >= 3
AND
failure_class == mandate_cancelled
```

then:

```text
intervention = stop
reason = "mandate cancelled after repeated failures, retrying is not viable — requires customer to re-authorize"
```

### Rule 3 — Cooldown

If a retry was attempted for the same case during the last 24 hours, then:

```text
intervention = stop
reason = "cooldown period active, stopping rule applied"
```

The cooldown information comes from the relevant audit history.

### Rule 4 — High recoverability

If:

```text
score.recoverability >= 0.7
```

then:

```text
intervention = retry_now
```

### Rule 5 — Moderate recoverability with available budget

If:

```text
0.4 <= score.recoverability < 0.7
AND
remaining_escalation_budget > estimated_cost
```

then:

```text
intervention = send_message
```

Deduct the estimated cost from the batch budget.

### Rule 6 — Moderate recoverability with insufficient budget

If:

```text
0.4 <= score.recoverability < 0.7
AND
remaining_escalation_budget <= estimated_cost
```

then:

```text
intervention = stop
reason = "recovery budget exhausted for this batch"
```

### Rule 7 — Low recoverability

Otherwise:

```text
intervention = stop
reason = "low recoverability, action not justified"
```

---

# 10. Batch Budget

Use a simple `BatchBudget` dataclass.

It tracks a hard maximum for escalation spending during a batch.

Example configurable cap:

```text
₹5,000
```

The budget must provide a clear proof that recovery actions are bounded by cost limits.

Required tests must prove:

- the budget is never exceeded across a full batch;
- cooldown rules are respected;
- `mandate_cancelled` cases with three or more prior failures are always stopped and never retried.

---

# 11. Message Service

Create:

`message_service.py`

This service is called only when:

```text
intervention == send_message
```

The LLM receives only:

```text
failure_class
amount
customer_tenure_months
```

Do not send:

- raw case ID;
- internal policy reasoning;
- intervention selection logic;
- budget information.

The LLM can receive a prompt such as:

> Write a brief, non-pushy payment recovery message for a subscription payment that failed due to {failure_class}. Do not mention a discount or specific amount unless told to.

Store the generated result in the `Message` table.

The intervention must already have been selected before this service runs.

---

# 12. Audit Service

Create:

`audit_service.py`

This service writes append-only audit records.

Create an audit event for:

- diagnosis;
- scoring;
- policy decision;
- customer message;
- batch summary.

Do not create update or delete API routes for `AuditLog`.

---

# 13. Metrics Service

Create:

`metrics_service.py`

For every completed batch, calculate and store the following.

## Total at-risk amount

```text
sum(amount for all cases in batch)
```

## Total recovered amount

Sum the case amounts where:

```text
true_recoverable == True
```

and the selected intervention is one of:

```text
retry_now
retry_after_cooldown
send_message
```

## Total cost

```text
sum(budget_consumed)
```

## Net recovered

```text
total_recovered_amount - total_cost
```

## Recovery rate

```text
recovered cases / total cases
```

## Baseline recovery rate

Calculate the recovery rate that would have occurred if every case had simply been retried once.

Use:

```text
true_would_recover_without_action
```

This provides the baseline comparison.

## False-positive cost

Calculate cost spent on cases where:

```text
true_recoverable == False
```

## Cases blocked by stopping rules

Count cases where:

```text
decision == stop
```

---

# 14. API Endpoints

## Run a batch

```text
POST /batches/run
```

Run the full pipeline over `N` unprocessed cases.

Return the `BatchRun` summary.

## Get batch details

```text
GET /batches/{id}
```

Return the batch summary.

## Get case details

```text
GET /cases/{id}
```

Return:

- case information;
- diagnosis;
- score;
- policy decision;
- message;
- complete chronological audit trail.

The policy decision reason must be visible.

## Filter cases

```text
GET /cases?status=&failure_class=
```

Return a filtered case list for the dashboard.

## Segment breakdown

```text
GET /batches/{id}/segments
```

Break down:

- recovery rate;
- cost;

by:

- `failure_class`;
- `prior_failure_count` bucket.

This endpoint must expose the deliberate failure segment through the API rather than relying on a hardcoded screenshot.

## State restrictions

Do not add PUT or DELETE endpoints for:

- audit history;
- case history.

State should move forward through the pipeline.

---

# 15. Frontend

Build exactly **three screens**.

Do not add additional product screens.

## 1. Dashboard

Show:

- at-risk amount;
- recovered amount;
- net recovered;
- recovery rate compared with baseline;
- remaining escalation budget.

Also show a small bar chart comparing recovery rate and cost by:

```text
failure_class
```

## 2. Case Explorer

Provide a filterable and sortable case table.

When a user selects a case, show the chronological sequence:

```text
diagnosis
→ score
→ policy decision
→ message
→ outcome
```

The policy decision reason must be visible.

## 3. Batch Runner

Provide a button that calls:

```text
POST /batches/run
```

Show progress.

After completion, redirect to the Dashboard and show the new batch numbers.

## Design scope

Keep the interface:

- simple;
- clean;
- functional.

Do not spend more than one day on styling.

The project is not intended to be a design competition.

---

# 16. Testing Requirements

## Policy engine tests

Use `pytest` to cover every policy rule branch.

Include a simulated batch of 500 random cases and assert that:

```text
budget consumption never exceeds the configured cap
```

Also test:

- cooldown behavior;
- repeated mandate cancellation behavior;
- all rule branches.

## Metrics golden test

Create one hand-calculated fixture containing five cases with known outcomes.

Assert exact metric values from `metrics_service.py`.

## Integration test

Run 20 synthetic cases through the full pipeline.

Assert that every case has a:

```text
complete
non-empty
audit trail
```

---

# 17. Required Documented Failure

This failure is a required part of the deliverable.

Do not skip it.

## Step 1 — Run the untuned version

Run the full pipeline using the original scorer and policy configuration.

## Step 2 — Inspect segments

Use:

```text
GET /batches/{id}/segments
```

Inspect the segment:

```text
insufficient_funds
AND
prior_failure_count >= 3
```

Confirm that this segment receives `send_message` interventions and produces:

```text
negative recovered-minus-cost performance
```

The overall batch may still look successful.

The problem must be found through segment-level metrics, not just overall metrics.

## Step 3 — Document what happened

Create:

```text
docs/what-broke.md
```

Document:

1. what failed;
2. how it was discovered;
3. the before numbers;
4. the policy change;
5. the after numbers.

The policy change is:

```text
insufficient_funds
AND
prior_failure_count >= 3
```

requires:

```text
score.recoverability >= 0.85
```

before allowing `send_message`.

Otherwise:

```text
stop
```

## Step 4 — Preserve both runs

Keep both:

- the original batch with the failure;
- the batch after the fix.

Do not delete the original bad `BatchRun`.

Both records must remain available for the live demo.

---

# 18. Required Build Order

Build and verify the project in this exact sequence.

## Step 1 — Repository scaffold

Create:

- FastAPI application skeleton;
- SQLAlchemy models;
- simple `create_all` database setup;
- health-check endpoint.

Do not use Alembic for this project.

Verify:

```text
uvicorn app.main:app
```

runs successfully and:

```text
GET /health
```

returns HTTP 200.

## Step 2 — Synthetic data

Build:

```text
generate_data.py
```

Generate and inspect the synthetic dataset.

Use a quick pandas group-by to verify that the deliberate failure segment exists.

## Step 3 — Train the scorer

Build:

```text
train_scorer.py
```

Train the model, evaluate it, save:

```text
models/scorer.pkl
```

and write:

```text
docs/eval-report.md
```

## Step 4 — Policy engine

Build:

```text
policy_engine.py
```

and complete all related pytest tests.

All tests for this module must pass before moving on.

This is the core dependency for the rest of the system.

## Step 5 — Diagnosis service

Build:

```text
diagnosis_service.py
```

Include:

- LLM integration;
- schema validation;
- one retry;
- deterministic fallback.

## Step 6 — Message service

Build:

```text
message_service.py
```

The LLM must only generate the message text.

## Step 7 — Audit and metrics

Build:

```text
audit_service.py
metrics_service.py
```

## Step 8 — Pipeline and batch execution

Connect the system through:

```text
pipeline.py
```

Create one function that processes a single case end to end.

Then implement:

```text
POST /batches/run
```

## Step 9 — Demonstrate the deliberate failure

Run a full batch.

Confirm that the failure segment appears through:

```text
GET /batches/{id}/segments
```

## Step 10 — Apply the documented fix

Apply the policy change described in the documented failure section.

Run another batch.

Confirm improvement.

Write:

```text
docs/what-broke.md
```

with real before-and-after numbers.

## Step 11 — Remaining API endpoints

Implement the remaining endpoints.

## Step 12 — Frontend

Build and connect exactly the three required screens.

## Step 13 — README

Write `README.md` covering:

- architecture;
- major decisions;
- why a tabular ML model is used instead of an LLM for scoring;
- why the LLM cannot make money-affecting decisions;
- how to run the application;
- evaluation results;
- a link to `docs/what-broke.md`.

## Step 14 — Final demo batch

Run the final full batch used for the demo recording.

---

# 19. Definition of Done

The project is complete only when all of the following are true.

## Application startup

Both the backend and frontend start successfully.

The backend command:

```text
uvicorn app.main:app
```

must work without manual database setup beyond running:

```text
generate_data.py
```

once.

## Tests

`pytest` passes, including:

- policy-engine rule tests;
- budget invariant tests;
- cooldown tests;
- stopping-rule tests;
- metrics golden test;
- integration test.

## Full batch execution

A batch containing at least **300 cases** can run end to end.

Every case must have a complete audit trail.

Target:

```text
100% audit trail coverage
```

## Required documents

Both files must exist and contain real numbers:

```text
docs/eval-report.md
docs/what-broke.md
```

Do not use placeholder metrics.

## Dashboard traceability

Every number shown on the Dashboard must be traceable to a specific:

```text
BatchRun
```

record.

No dashboard metric may be hardcoded.

---

# 20. Final Product Boundary

The main idea of RENEW is:

> Use deterministic, auditable rules to control subscription payment recovery while using AI only for ambiguous classification and customer-facing wording.

The system is not an autonomous payment decision-maker.

The LLM does not control:

- money;
- retries;
- escalation;
- stopping;
- budget.

The recoverability model estimates probability.

The policy engine makes the actual intervention decision.

The audit trail records every important step.

The batch metrics show whether the recovery strategy performs better than a simple retry-everything baseline.

The documented failure proves that the system is evaluated honestly at the segment level, not only by attractive overall numbers.
