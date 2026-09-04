"""Database engine / session setup for RENEW.

SQLite via SQLAlchemy 2.0. `create_all` is used deliberately (no Alembic)
per the build spec: this is a hackathon-scale project where schema churn is
handled by regenerating the synthetic dataset, not by migrations.
"""

from __future__ import annotations

import os
from pathlib import Path

from sqlalchemy import create_engine, event
from sqlalchemy.engine import Engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker


class Base(DeclarativeBase):
    """Declarative base for all RENEW models."""


# Allow deployments (Render / Railway / Fly) to point the SQLite file at a
# persistent disk (e.g. /data on Render). In local dev the default
# `<repo>/data/` is used, which is what the rest of the scripts assume.
_default_data_dir = Path(__file__).resolve().parent.parent / "data"
DATA_DIR = Path(os.environ.get("RENEW_DATA_DIR", str(_default_data_dir)))
DATA_DIR.mkdir(parents=True, exist_ok=True)

# Same idea for the trained scorer pickle and the failure-story JSON.
_default_models_dir = Path(__file__).resolve().parent.parent / "models"
MODELS_DIR = Path(os.environ.get("RENEW_MODELS_DIR", str(_default_models_dir)))
MODELS_DIR.mkdir(parents=True, exist_ok=True)

DATABASE_URL = os.environ.get(
    "RENEW_DATABASE_URL",
    f"sqlite:///{DATA_DIR / 'renew.db'}",
)

engine: Engine = create_engine(
    DATABASE_URL,
    connect_args={"check_same_thread": False},  # FastAPI runs handlers across threads
)


@event.listens_for(Engine, "connect")
def _set_sqlite_pragma(dbapi_connection, connection_record):  # noqa: ANN001
    """Enable FK enforcement + WAL for concurrent reads during a batch run."""
    cursor = dbapi_connection.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA journal_mode=WAL")
    cursor.close()


SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)


def get_db() -> Session:
    """FastAPI dependency yielding a scoped session."""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db() -> None:
    """Create all tables. Called from app startup and by tests/scripts."""
    from app import models  # noqa: F401  (register mappers before create_all)

    Base.metadata.create_all(bind=engine)
