# What Broke — the deliberate failure segment, found and fixed

This document records a real failure of RENEW's first configuration: how it
was produced, how it was discovered through segment-level metrics, and what
the policy change did to contain it. Both `BatchRun` rows are preserved in
the database for the live demo (`data/failure_demo.json` holds this summary).

## 1. What failed

The untuned recoverability scorer is an additive logistic-regression model.
In our synthetic-but-realistic data, repeated prior failures move two large
segments in OPPOSITE directions:

- `bank_decline` customers with many prior failures often recover on retry
  (declines are partly random);
- `insufficient_funds` customers with **>= 3 prior failures almost never
  recover** (the underlying problem is chronic), and their tickets skew
  small (Rs 149-1600).

An additive model cannot represent that interaction: the positive and
negative effects of `prior_failure_count` largely cancel in its linear
coefficient. Meanwhile long customer tenure correlates positively with
recovery AND with having failed many times. Net effect: the scorer assigned
moderate scores (~0.42 mean) to cases in the failure segment

> `failure_class = insufficient_funds AND prior_failure_count >= 3`

which landed them squarely in the policy's `send_message` band
(0.40 <= score < 0.70). The system dutifully paid ~Rs 300 of outreach cost
per case for customers who were mostly gone.

## 2. How it was discovered

Not by looking at overall numbers — those were flattering:

| BatchRun (before fix) | value |
|---|---|
| total_cases | 300 |
| at-risk amount | Rs 652,602.57 |
| recovered | Rs 244,769.48 |
| total cost | Rs 4,800 |
| **net recovered** | **+Rs 239,969.48** |
| recovery rate vs baseline | 27.0% vs 14.3% |

The problem surfaced via `GET /batches/{id}/segments`, which breaks metrics
down per `failure_class` and per `prior_failure_count` bucket:

| Segment (`class:insufficient_funds\|pfc>=3`) | before fix |
|---|---|
| cases | 56 |
| recovered cases / amount | 1 case / Rs 1,293.32 |
| outreach cost spent | Rs 1,800.00 |
| **net recovered** | **-Rs 506.68** |
| segment recovery rate | 1.79% |

A 300-case batch can look like a success while one segment quietly destroys
value. Overall metrics hid it; the segments endpoint exposed it. This is why
the endpoint exists and why it is part of the Definition of Done.

## 3. The policy change

The fix is deliberately NOT a model change (that would hide the lesson).
It is a deterministic, auditable rule added to `policy_engine.py`:

> For `failure_class == insufficient_funds AND prior_failure_count >= 3`,
> allow `send_message` only when `score.recoverability >= 0.85`;
> otherwise `stop`.

The rule sits after the safety rules (low confidence, mandate cancellation,
cooldown) and before the generic scoring bands, and every decision it makes
records its reason in the audit trail. It is toggled per-batch via the
`segment_send_threshold` parameter of `POST /batches/run`
(`null` = original behaviour, `0.85` = fix).

## 4. After numbers

Second batch (next 200 unprocessed cases, same scorer, hardened rule):

| metric | before fix (300 cases) | after fix (200 cases) |
|---|---|---|
| net recovered (batch) | +Rs 239,969.48 | +Rs 116,985.09 |
| recovery rate vs baseline | 27.0% vs 14.3% | 28.0% vs 14.5% |
| false-positive cost | Rs 1,800 | Rs 1,500 |
| blocked by stopping rules | 174 | 115 |

Failure segment after the fix:

| Segment (`class:insufficient_funds\|pfc>=3`) | before | after |
|---|---|---|
| cases | 56 | 32 |
| outreach cost | Rs 1,800.00 | **Rs 0.00** |
| net recovered | **-Rs 506.68** | **Rs 0.00** (no waste) |

The negative-net bleed is eliminated; genuinely high-score (>0.85) segment
cases would still be allowed through, so the stop is bounded rather than
absolute. Note the after-run processes fewer cases because both runs share
one finite pool of synthetic 'new' cases — both `BatchRun` rows remain
queryable via `GET /batches/{id}` and `/segments`.

## 5. Honest limitations

- The scorer itself is unchanged; a nonlinear model (e.g. gradient boosting)
  could learn the interaction directly. We kept v1 simple on purpose: the
  policy guard is cheap, interpretable and auditable, and upgrading the
  model is tracked as future work (see README).
- Ground truth here is synthetic by design (hackathon constraint); real
  deployments must derive `true_recoverable` labels from actual retry
  outcomes over time.
