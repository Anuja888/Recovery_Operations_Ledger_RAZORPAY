"""Train the tabular recoverability classifier.

Why scikit-learn and not an LLM here (see README for full rationale):
the dataset is small (hundreds of rows), fully tabular, with a well-defined
binary target. A gradient-boosted tree gives calibrated probabilities,
reproducibility, sub-millisecond inference, per-feature explanations, and a
proper train/val/test evaluation protocol -- none of which an LLM provides.

Features (spec): failure_class, amount, customer_tenure_months,
prior_failure_count, payment_method, merchant_category.
Target (eval-only): true_recoverable. Ground truth NEVER reaches runtime.

Run:  python -m app.train_scorer
Outputs: models/scorer.pkl + docs/eval-report.md (real numbers).
"""

from __future__ import annotations

import json
from pathlib import Path

import joblib
import pandas as pd
from sklearn.compose import ColumnTransformer
from sklearn.inspection import permutation_importance
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import (
    average_precision_score,
    classification_report,
    precision_recall_fscore_support,
    roc_auc_score,
)
from sklearn.pipeline import Pipeline
from sklearn.preprocessing import OneHotEncoder, StandardScaler

ROOT = Path(__file__).resolve().parent.parent
MODEL_PATH = ROOT / "models" / "scorer.pkl"
REPORT_PATH = ROOT / "docs" / "eval-report.md"

CATEGORICAL = ["failure_class", "payment_method", "merchant_category"]
NUMERIC = ["amount", "customer_tenure_months", "prior_failure_count"]
FEATURES = CATEGORICAL + NUMERIC
TARGET = "true_recoverable"
MODEL_VERSION = "logreg-v1"


def _load() -> tuple[pd.DataFrame, pd.DataFrame, pd.DataFrame]:
    df = pd.read_csv(ROOT / "data" / "cases.csv", dtype={"case_id": str})
    splits = json.loads((ROOT / "data" / "splits.json").read_text())
    df["split"] = df["case_id"].astype(str).map(splits)
    if df["split"].isna().any():
        raise RuntimeError("splits.json does not cover every case_id -- regenerate data")
    # leakage-free splits keyed by case_id
    parts = {s: df[df["split"] == s].reset_index(drop=True) for s in ("train", "val", "test")}
    return parts["train"], parts["val"], parts["test"]


def _build_pipeline() -> Pipeline:
    pre = ColumnTransformer(
        transformers=[
            ("cat", OneHotEncoder(handle_unknown="ignore"), CATEGORICAL),
            ("num", StandardScaler(), NUMERIC),
        ]
    )
    # v1 model is deliberately SIMPLE (untuned baseline): a linear model
    # cannot represent the (insufficient_funds AND prior_failure_count >= 3)
    # interaction, so the deliberate failure segment -- whose visible features
    # look attractive thanks to long tenure -- scores moderately recoverable.
    # This is precisely the documented failure in docs/what-broke.md; a later,
    # tuned nonlinear model would fit it better and that upgrade path is
    # discussed in the README.
    clf = LogisticRegression(max_iter=1000, random_state=42)
    return Pipeline([("pre", pre), ("clf", clf)])


def _calibration_table(y_true, proba, bins: int = 5) -> pd.DataFrame:
    df = pd.DataFrame({"p": proba, "y": y_true})
    df["bucket"] = pd.cut(df["p"], bins=bins, labels=False)
    grouped = df.groupby("bucket").agg(
        predicted_mean=("p", "mean"), actual_rate=("y", "mean"), n=("y", "size")
    )
    return grouped.round(3)


def main() -> None:
    train, val, test = _load()
    pipe = _build_pipeline()

    pipe.fit(train[FEATURES], train[TARGET])

    val_proba = pipe.predict_proba(val[FEATURES])[:, 1]
    print("validation AUC:", round(roc_auc_score(val[TARGET], val_proba), 4))

    test_proba = pipe.predict_proba(test[FEATURES])[:, 1]
    test_pred = (test_proba >= 0.5).astype(int)
    precision, recall, f1, _ = precision_recall_fscore_support(
        test[TARGET], test_pred, average="binary", zero_division=0
    )
    auc = roc_auc_score(test[TARGET], test_proba)
    pr_auc = average_precision_score(test[TARGET], test_proba)
    calib = _calibration_table(test[TARGET].to_numpy(), test_proba)

    # permutation importance on the validation split, aggregated to original
    # feature names (stored in the bundle for runtime `top_features`)
    perm = permutation_importance(
        pipe, val[FEATURES], val[TARGET], n_repeats=8, random_state=42
    )
    importances = sorted(
        zip(FEATURES, perm.importances_mean), key=lambda kv: -kv[1]
    )
    imp_total = sum(v for _, v in importances) or 1.0
    feature_importances = {k: round(v / imp_total, 4) for k, v in importances}

    MODEL_PATH.parent.mkdir(exist_ok=True)
    joblib.dump(
        {
            "pipeline": pipe,
            "model_version": MODEL_VERSION,
            "features": FEATURES,
            "feature_importances": feature_importances,
        },
        MODEL_PATH,
    )

    REPORT_PATH.parent.mkdir(exist_ok=True)
    lines = [
        "# Recoverability Scorer — Evaluation Report",
        "",
        f"- Model: `{MODEL_VERSION}` (LogisticRegression + one-hot/scaled pipeline, deliberately untuned v1)",
        f"- Trained on: {len(train)} rows (train split by case_id; val={len(val)}, test={len(test)})",
        f"- Features: `{', '.join(FEATURES)}`",
        f"- Target: `true_recoverable` (hidden synthetic ground truth — used ONLY for training/eval)",
        "",
        "## Held-out test metrics (threshold = 0.5)",
        "",
        f"| Metric | Value |",
        f"|---|---|",
        f"| Precision | {precision:.4f} |",
        f"| Recall | {recall:.4f} |",
        f"| F1 | {f1:.4f} |",
        f"| ROC-AUC | {auc:.4f} |",
        f"| PR-AUC | {pr_auc:.4f} |",
        "",
        "## Calibration check (predicted probability bucket vs actual recovery rate)",
        "",
        calib.to_markdown(),
        "",
        "## Permutation feature importance (validation split, normalized)",
        "",
        "\n".join(f"- `{k}`: {v}" for k, v in feature_importances.items()),
        "",
        "## Known limitation",
        "",
        "The deliberate failure segment (`insufficient_funds` AND `prior_failure_count >= 3`)"
        " has deceptively attractive visible features (long tenure). An untuned model tends to"
        " score many of those cases moderately high because `prior_failure_count >= 3` is rare"
        " enough that trees split on tenure instead. See `docs/what-broke.md` for how this"
        " manifests in batch metrics and the policy fix that contains it.",
        "",
    ]
    REPORT_PATH.write_text("\n".join(lines))
    print(f"saved {MODEL_PATH}")
    print(f"wrote {REPORT_PATH}")
    print(f"test: precision={precision:.4f} recall={recall:.4f} f1={f1:.4f} auc={auc:.4f}")


if __name__ == "__main__":
    main()
