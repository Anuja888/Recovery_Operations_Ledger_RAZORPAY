"""Runtime scoring interface.

`score(case_features) -> float` returns the predicted recoverability
probability (0-1) for a case. Ground-truth fields are explicitly rejected:
the scorer must never see `true_recoverable` /
`true_would_recover_without_action`.

Also exposes aggregated per-feature contributions derived from the trained
model's one-hot feature importances.
"""

from __future__ import annotations

import os
import threading
from functools import lru_cache
from pathlib import Path

import joblib

ROOT = Path(__file__).resolve().parent.parent
MODEL_PATH = Path(os.environ.get("RENEW_MODELS_DIR", str(ROOT / "models"))) / "scorer.pkl"

# ground truth must never be fed to the model
FORBIDDEN_FEATURES = {"true_recoverable", "true_would_recover_without_action"}

_lock = threading.Lock()
_cached = None


def _load_model():
    global _cached
    if _cached is None:
        with _lock:
            if _cached is None:
                if not MODEL_PATH.exists():
                    raise FileNotFoundError(
                        f"{MODEL_PATH} not found -- run `python -m app.train_scorer` first"
                    )
                _cached = joblib.load(MODEL_PATH)
    return _cached


def score(case_features: dict) -> float:
    """Predict recoverability probability in [0, 1] for one case.

    Expected keys: failure_class, amount, customer_tenure_months,
    prior_failure_count, payment_method, merchant_category.
    """
    bundle = _load_model()
    feats = dict(case_features)
    leaked = FORBIDDEN_FEATURES.intersection(feats)
    if leaked:
        raise ValueError(f"ground-truth fields must never reach the scorer: {sorted(leaked)}")
    missing = set(bundle["features"]) - set(feats)
    if missing:
        raise ValueError(f"missing required features: {sorted(missing)}")
    row = {k: feats[k] for k in bundle["features"]}
    import pandas as pd

    proba = bundle["pipeline"].predict_proba(pd.DataFrame([row]))[0, 1]
    return float(proba)


@lru_cache(maxsize=4)
def feature_importances() -> dict[str, float]:
    """Permutation importance computed on the validation split at train time,
    stored in the model bundle."""
    bundle = _load_model()
    return dict(bundle.get("feature_importances", {}))


def top_features(k: int = 3) -> dict[str, float]:
    imp = feature_importances()
    return dict(list(imp.items())[:k])
