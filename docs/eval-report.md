# Recoverability Scorer — Evaluation Report

- Model: `logreg-v1` (LogisticRegression + one-hot/scaled pipeline, deliberately untuned v1)
- Trained on: 1400 rows (train split by case_id; val=300, test=300)
- Features: `failure_class, payment_method, merchant_category, amount, customer_tenure_months, prior_failure_count`
- Target: `true_recoverable` (hidden synthetic ground truth — used ONLY for training/eval)

## Held-out test metrics (threshold = 0.5)

| Metric | Value |
|---|---|
| Precision | 0.7982 |
| Recall | 0.6319 |
| F1 | 0.7054 |
| ROC-AUC | 0.7383 |
| PR-AUC | 0.6998 |

## Calibration check (predicted probability bucket vs actual recovery rate)

|   bucket |   predicted_mean |   actual_rate |   n |
|---------:|-----------------:|--------------:|----:|
|        0 |            0.161 |         0.259 |  81 |
|        1 |            0.328 |         0.296 |  71 |
|        2 |            0.472 |         0.391 |  46 |
|        3 |            0.698 |         1     |  16 |
|        4 |            0.828 |         0.791 |  86 |

## Permutation feature importance (validation split, normalized)

- `failure_class`: 0.9086
- `prior_failure_count`: 0.1907
- `amount`: 0.0117
- `merchant_category`: -0.0
- `payment_method`: -0.0409
- `customer_tenure_months`: -0.07

## Known limitation

The deliberate failure segment (`insufficient_funds` AND `prior_failure_count >= 3`) has deceptively attractive visible features (long tenure). An untuned model tends to score many of those cases moderately high because `prior_failure_count >= 3` is rare enough that trees split on tenure instead. See `docs/what-broke.md` for how this manifests in batch metrics and the policy fix that contains it.
