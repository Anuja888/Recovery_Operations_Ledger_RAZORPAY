"""Synthetic data generation for RENEW.

Generates 400-600 `Case` rows (default: 500) with:

- ~70% structured `failure_code` (deterministic mapping to failure class),
  ~30% free-text `failure_message` (requires LLM diagnosis fallback);
- failure-class distribution skewed toward insufficient_funds /
  bank_decline, away from mandate_cancelled / expired_card;
- HIDDEN ground truth (`true_recoverable`,
  `true_would_recover_without_action`) produced by a hidden noisy function
  of case features -- never exposed to scorer or policy engine;
- a DELIBERATE FAILURE SEGMENT: insufficient_funds AND prior_failure_count
  >= 3 has disproportionately LOW true recoverability while its visible
  features (long tenure etc.) look deceptively good, so an untuned model
  will over-retry / over-message it. This powers docs/what-broke.md.
- a leakage-free 70/15/15 train/val/test split by case_id (data/splits.json).

Outputs: rows inserted into SQLite + data/cases.csv + data/splits.json.

Run:  python -m app.generate_data [--n 500] [--seed 42]
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import random
from datetime import datetime, timedelta, timezone
from pathlib import Path

from app.database import SessionLocal, init_db
from app.models import Case

FAILURE_CODE_MAP = {
    "card_expired": "expired_card",
    "expired_card": "expired_card",
    "insufficient_funds": "insufficient_funds",
    "nsf": "insufficient_funds",
    "bank_decline_0551": "bank_decline",
    "do_not_honor": "bank_decline",
    "issuer_unavailable": "bank_decline",
    "mandate_revoked": "mandate_cancelled",
    "customer_stopped_mandate": "mandate_cancelled",
}

FREE_TEXT_BY_CLASS = {
    "expired_card": [
        "Card has expired, please update your card.",
        "The expiry date on file has passed.",
    ],
    "insufficient_funds": [
        "Account balance was too low for this charge.",
        "Customer does not have enough funds right now.",
    ],
    "bank_decline": [
        "The issuing bank declined the transaction without a specific reason.",
        "Payment blocked by the bank's fraud rules.",
    ],
    "mandate_cancelled": [
        "The autopay mandate was cancelled by the customer.",
        "Customer revoked the e-mandate at their bank.",
    ],
    # deliberately ambiguous texts -> exercise the LLM + unknown fallback
    "ambiguous": [
        "Something went wrong while processing, not sure what happened.",
        "Transaction failed. Gateway returned a generic error.",
        "Could not complete the payment this time.",
    ],
}

PAYMENT_METHODS = ["card", "upi", "netbanking", "wallet", "emandate"]
MERCHANT_CATEGORIES = ["saas", "ott", "ecommerce", "edtech", "fitness"]


def _pick_failure_class(rng: random.Random) -> str:
    """Skewed distribution: IF/BD common, EC/MC less common."""
    roll = rng.random()
    if roll < 0.34:
        return "insufficient_funds"
    if roll < 0.64:
        return "bank_decline"
    if roll < 0.82:
        return "mandate_cancelled"
    return "expired_card"


# Cap how many cases are flagged is_failure_segment=True. Keeping this
# small (~50 in 2000 = 2.5%) means the trained v1 additive scorer cannot
# learn the (insufficient_funds ∧ prior_failure_count>=3) interaction
# robustly from this training data -- it therefore falls back to scoring
# the segment moderately (the documented v1 failure).
SEGMENT_CAP = 50


def _hidden_recover_probability(case_like: dict) -> float:
    """HIDDEN ground-truth function. Never visible to scorer/policy."""
    fc = case_like["failure_class"]
    tenure = case_like["customer_tenure_months"]
    pfc = case_like["prior_failure_count"]
    amount = case_like["amount"]

    z = -0.6
    if fc == "insufficient_funds":
        z += 0.9
    elif fc == "bank_decline":
        z += 0.7
    elif fc == "expired_card":
        z -= 1.1
    elif fc == "mandate_cancelled":
        z -= 1.9
    z += min(tenure, 50) * 0.025         # long tenure helps a LOT (normally)
    if amount > 20000:
        z -= 0.5                         # big tickets are harder to save

    # INTERACTION hidden from additive models: repeated failures behave
    # OPPOSITELY across the two high-frequency failure classes --
    #   * bank_decline: persistent retrying eventually passes (+)
    #   * insufficient_funds AND prior_failure_count >= 3: collapses (-)
    # An untuned ADDITIVE scorer (logistic regression v1) sees the effects
    # cancel in its linear pfc coefficient and therefore scores the
    # deliberate failure segment as moderately recoverable -- the documented
    # failure of docs/what-broke.md.
    if fc == "insufficient_funds" and pfc >= 3:
        z -= 3.0
    elif fc == "bank_decline" and pfc >= 3:
        z += 2.9
    return 1.0 / (1.0 + math.exp(-z))


def _make_case(rng: random.Random) -> dict:
    """Build one raw case dict."""
    failure_class = _pick_failure_class(rng)

    prior_failure_count = rng.choices(
        [0, 1, 2, 3, 4, 5], weights=[38, 25, 15, 10, 7, 5]
    )[0]
    # Repeat failures cluster in the two big payment-failure classes: both
    # insufficient_funds and bank_decline get a heavy high-failure subgroup
    # (their hidden outcomes move in OPPOSITE directions -- see
    # _hidden_recover_probability -- which is what hides the failure segment
    # from an additive scorer).
    if failure_class in ("insufficient_funds", "bank_decline") and rng.random() < 0.45:
        prior_failure_count = rng.choice([3, 4, 5])

    tenure_pool = ([1, 3, 6, 12, 24, 36, 48, 60]
                   if rng.random() < 0.5 else list(range(1, 61)))
    customer_tenure_months = rng.choice(tenure_pool)
    # realistic correlation: the longer a subscription has existed, the more
    # chances it had to fail -- repeat failures come with longer tenure
    customer_tenure_months = min(72,
        customer_tenure_months + prior_failure_count * rng.randint(4, 10))
    amount = round(min(max(rng.lognormvariate(7.3, 0.9), 99), 60000), 2)
    # The deliberate failure segment skews to SMALL tickets (long-failing
    # small subscriptions): with ~10-15% true recoverability, expected
    # recovery per case (~Rs 150-250) is far below outreach cost -- so
    # mass-messaging this segment destroys net recovered.
    if failure_class == "insufficient_funds" and prior_failure_count >= 3:
        amount = round(rng.uniform(149, 1600), 2)

    case = {
        "subscription_id": f"sub_{rng.randint(100000, 999999)}",
        "merchant_id": f"m_{rng.randint(1000, 1999)}",
        "amount": amount,
        "currency": "INR",
        "failure_class": failure_class,
        "customer_tenure_months": customer_tenure_months,
        "prior_failure_count": prior_failure_count,
        "payment_method": rng.choice(PAYMENT_METHODS),
        "merchant_category": rng.choice(MERCHANT_CATEGORIES),
    }

    # ~70% structured code / ~30% free text
    if rng.random() < 0.70:
        codes = [c for c, fc in FAILURE_CODE_MAP.items() if fc == failure_class]
        case["failure_code"] = rng.choice(codes)
        case["failure_message"] = None
    else:
        pool = (FREE_TEXT_BY_CLASS[failure_class]
                if rng.random() < 0.75 else FREE_TEXT_BY_CLASS["ambiguous"])
        case["failure_code"] = None
        case["failure_message"] = rng.choice(pool)
    return case


def _ground_truth(case: dict, rng: random.Random) -> tuple[bool, bool]:
    p = _hidden_recover_probability(case)
    # heavy label noise: an untuned model cannot fully recover the segment
    # interaction and will lean on the globally attractive tenure signal
    true_recoverable = rng.random() < max(0.02, min(0.98, p + rng.gauss(0, 0.12)))
    # Baseline: a blind retry only succeeds for a minority of recoverable cases.
    baseline_p = 0.35 * p + 0.03
    twr = true_recoverable and rng.random() < baseline_p + 0.05
    return true_recoverable, twr


def _assign_splits(n: int, seed: int) -> dict[str, str]:
    """Deterministic leakage-free split keyed by list position -> case_id."""
    idx = list(range(n))
    rng = random.Random(seed + 1)
    rng.shuffle(idx)
    n_train = int(n * 0.70)
    n_val = int(n * 0.15)
    splits: dict[str, str] = {}
    for pos, i in enumerate(idx):
        if pos < n_train:
            splits[str(i)] = "train"
        elif pos < n_train + n_val:
            splits[str(i)] = "val"
        else:
            splits[str(i)] = "test"
    return splits


def _insert_cases(rng: random.Random, base_id: int, base_time: datetime,
                  count: int, prefix: str | None = None) -> tuple[list[Case], list[str]]:
    """Insert `count` fresh 'new' cases; return (case_objs, generator_classes).

    Does NOT touch existing rows or artifacts. Used by `top_up`.

    Case IDs are `prefix + (base_id + i):07d`, so they're unique within a
    single call. `prefix` defaults to a fresh 5-digit RNG value; callers
    that need a collision-safe prefix (e.g. `top_up`) can pass one in.
    """
    prefix = f"{rng.randint(10000, 99999):05d}"
    cases: list[Case] = []
    classes: list[str] = []
    for i in range(count):
        raw = _make_case(rng)
        fc = raw.pop("failure_class")
        # Mark the deliberate failure segment for guaranteed-minimum
        # sampling by the failure-story rerun path. This marker is a
        # generation bookkeeping field — never passed to the scorer and
        # never read by the policy engine. We cap how many cases get
        # flagged (SEGMENT_CAP) so the trained v1 additive scorer cannot
        # learn the segment interaction robustly; with a small
        # segment-to-pool ratio the v1 model falls back to scoring the
        # segment moderately, which is the documented v1 failure.
        is_segment_candidate = (
            fc == "insufficient_funds"
            and raw["prior_failure_count"] >= 3
            and 149 <= raw["amount"] <= 1600
        )
        is_segment = is_segment_candidate and (
            sum(1 for c in cases if c.is_failure_segment) < SEGMENT_CAP
        )
        tr, twr = _ground_truth({**raw, "failure_class": fc}, rng)
        case = Case(
            id=f"{prefix}{(base_id + i):07d}",
            created_at=base_time + timedelta(minutes=base_id + i),
            status="new",
            true_recoverable=tr,
            true_would_recover_without_action=twr,
            is_failure_segment=is_segment,
            **raw,
        )
        cases.append(case)
        classes.append(fc)
    return cases, classes


def generate(n: int = 500, seed: int = 42) -> list[Case]:
    """Wipe-and-rebuild the synthetic dataset (used by /admin/seed seed path)."""
    rng = random.Random(seed)
    init_db()
    db = SessionLocal()

    # regenerate from scratch for reproducibility; delete children first
    from app.models import AuditLog, BatchRun, Diagnosis, Message, PolicyDecision, Score

    for model in (AuditLog, Message, PolicyDecision, Score, Diagnosis,
                  BatchRun, Case):
        db.query(model).delete()

    base_time = datetime.now(timezone.utc) - timedelta(days=7)
    cases, classes = _insert_cases(rng, 0, base_time, n)
    db.add_all(cases)
    db.commit()

    data_dir = Path(__file__).resolve().parent.parent / "data"
    data_dir.mkdir(exist_ok=True)
    with open(data_dir / "cases.csv", "w", newline="") as f:
        w = csv.writer(f)
        w.writerow([
            "case_id", "failure_class", "amount", "customer_tenure_months",
            "prior_failure_count", "payment_method", "merchant_category",
            "has_structured_code", "true_recoverable",
            "true_would_recover_without_action",
        ])
        for c, fc in zip(cases, classes):
            w.writerow([
                c.id, fc, c.amount, c.customer_tenure_months,
                c.prior_failure_count, c.payment_method, c.merchant_category,
                int(c.failure_code is not None), int(c.true_recoverable),
                int(c.true_would_recover_without_action),
            ])

    with open(data_dir / "splits.json", "w") as f:
        pos_to_split = _assign_splits(len(cases), seed)
        json.dump({c.id: pos_to_split[str(i)] for i, c in enumerate(cases)}, f, indent=1)

    db.close()
    print(f"Generated {len(cases)} cases -> data/renew.db, data/cases.csv, data/splits.json")
    return cases


def top_up(n: int = 500, seed: int = 42) -> list[Case]:
    """Append `n` fresh 'new' cases WITHOUT touching existing rows or splits.

    Used by run-time auto-topup so the pool never runs dry. Returns the new
    case rows. Deliberately preserves the existing failure-class / segment
    distribution (uses the same _make_case / _hidden_recover_probability).
    """
    rng = random.Random(seed)
    db = SessionLocal()
    try:
        # IDs are 5-digit prefix + 7-digit counter. Both halves must be
        # strictly greater than anything currently in the table.
        existing_ids = [row[0] for row in db.query(Case.id).all() if row[0]]
        existing_prefixes = {cid[:5] for cid in existing_ids}
        existing_suffixes = []
        for cid in existing_ids:
            try:
                existing_suffixes.append(int(cid[-7:]))
            except ValueError:
                pass
        next_suffix = (max(existing_suffixes) + 1) if existing_suffixes else 0
        prefix = f"{rng.randint(10000, 99999):05d}"
        while prefix in existing_prefixes:
            prefix = f"{rng.randint(10000, 99999):05d}"
        base_time = datetime.now(timezone.utc)
        cases, _classes = _insert_cases(rng, next_suffix, base_time, n, prefix=prefix)
        db.add_all(cases)
        db.commit()
        return cases
    finally:
        db.close()


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate synthetic RENEW cases")
    parser.add_argument("--n", type=int, default=500)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    generate(n=args.n, seed=args.seed)


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Generate synthetic RENEW cases")
    parser.add_argument("--n", type=int, default=500)
    parser.add_argument("--seed", type=int, default=42)
    args = parser.parse_args()
    generate(n=args.n, seed=args.seed)
