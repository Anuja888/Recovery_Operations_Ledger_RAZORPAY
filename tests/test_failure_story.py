"""Tests for GET /failure-story and POST /failure-story/rerun."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from app.database import init_db
from app.models import Case
from app.routes import get_failure_story, post_failure_story_rerun
from fastapi import HTTPException

FAILURE_STORY_PATH = Path(__file__).resolve().parent.parent / "data" / "failure_demo.json"


def _make_cases(db, n: int = 600) -> list[str]:
    ids = []
    for i in range(n):
        case = Case(
            id=f"fs{i:04d}",
            subscription_id=f"sub_fs_{i}",
            merchant_id="m_fs",
            amount=500 + i * 137,
            failure_code="insufficient_funds",
            customer_tenure_months=(i * 5) % 60,
            prior_failure_count=i % 6,
            payment_method="card",
            merchant_category="saas",
            status="new",
            true_recoverable=bool(i % 3),
            true_would_recover_without_action=False,
        )
        db.add(case)
        ids.append(case.id)
    db.commit()
    return ids


def test_failure_story_404_when_missing(db_session):
    if FAILURE_STORY_PATH.exists():
        FAILURE_STORY_PATH.unlink()
    with pytest.raises(HTTPException) as exc:
        get_failure_story(db_session)
    assert exc.value.status_code == 404


def test_failure_story_rerun_creates_story_and_returns_it(db_session):
    """First rerun on a fresh DB pins canonical AND populates latest.
    Subsequent reruns leave canonical pinned and only refresh latest.
    """
    init_db()
    _make_cases(db_session, 600)
    resp = post_failure_story_rerun(db_session)
    db_session.commit()
    # canonical section is now populated (the first rerun pins it)
    assert resp.before is not None
    assert resp.after is not None
    assert resp.before["batch"]["total_cases"] == 300
    assert resp.after["batch"]["total_cases"] == 300
    assert resp.narrative is not None
    assert "what_happened" in resp.narrative
    # latest mirrors canonical on the first rerun
    assert resp.latest is not None
    assert resp.latest["before"]["batch"]["total_cases"] == 300
    assert FAILURE_STORY_PATH.exists()


def test_failure_story_rerun_auto_topups_when_pool_low(db_session):
    """Phase A change: post_failure_story_rerun auto-tops up the 'new' pool
    (via run_batch(300, auto_topup=True)) rather than failing outright when
    there aren't 600 fresh cases available. A 20-case seed should still
    produce a successful rerun that processes 300 cases on each side.
    """
    init_db()
    _make_cases(db_session, 20)
    resp = post_failure_story_rerun(db_session)
    db_session.commit()
    assert resp.before is not None and resp.after is not None
    assert resp.before["batch"]["total_cases"] == 300
    assert resp.after["batch"]["total_cases"] == 300


def test_failure_story_rerun_preserves_canonical_on_second_call(db_session):
    """Second rerun must NOT change the canonical numbers from the first.
    Only `latest` is updated.
    """
    init_db()
    _make_cases(db_session, 600)
    first = post_failure_story_rerun(db_session)
    db_session.commit()
    second = post_failure_story_rerun(db_session)
    db_session.commit()

    # Canonical numbers unchanged across reruns.
    assert first.before["batch"]["total_cases"] == second.before["batch"]["total_cases"]
    assert first.after["batch"]["total_cases"] == second.after["batch"]["total_cases"]
    assert first.before["batch"]["batch_id"] == second.before["batch"]["batch_id"]
    assert first.after["batch"]["batch_id"] == second.after["batch"]["batch_id"]
    assert first.before["batch"]["net_recovered"] == second.before["batch"]["net_recovered"]
    # Latest always present.
    assert second.latest is not None
    assert second.latest["before"]["batch"]["total_cases"] == 300
