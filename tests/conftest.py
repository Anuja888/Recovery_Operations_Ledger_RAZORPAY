"""Shared pytest fixtures: isolated SQLite DB per test."""

from __future__ import annotations

import os
import tempfile

import pytest

# must set env before importing app.database (it resolves the DB path)
_tmpdir = tempfile.mkdtemp(prefix="renew_test_")
os.environ["RENEW_DATABASE_URL"] = f"sqlite:///{_tmpdir}/test.db"

from app.database import SessionLocal, init_db  # noqa: E402


@pytest.fixture
def db_session():
    init_db()
    db = SessionLocal()
    try:
        yield db
    finally:
        # wipe all rows between tests for full isolation
        from app.models import AuditLog, BatchRun, Case, Diagnosis  # noqa: F401

        for table in ("audit_logs", "messages", "policy_decisions", "scores",
                      "diagnoses", "cases", "batch_runs"):
            db.execute(__import__("sqlalchemy").text(f"DELETE FROM {table}"))
        db.commit()
        db.close()
