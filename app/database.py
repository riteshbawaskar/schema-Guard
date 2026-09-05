"""SQLAlchemy engine/session for the application's own SQLite metadata store.

This is entirely separate from any external database being validated -
see app/connectors for runtime connections to target databases.
"""
from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import get_settings


class Base(DeclarativeBase):
    pass


_engine = None
_SessionLocal = None


def get_engine():
    global _engine
    if _engine is None:
        settings = get_settings()
        _engine = create_engine(
            settings.app_db_url,
            connect_args={"check_same_thread": False},
        )
    return _engine


def get_sessionmaker():
    global _SessionLocal
    if _SessionLocal is None:
        _SessionLocal = sessionmaker(bind=get_engine(), autoflush=False, autocommit=False)
    return _SessionLocal


def init_db() -> None:
    """Create all tables if they don't exist. Never drops existing data.

    Since the spec calls for a lightweight SQLite-backed app rather than a
    full migration framework, new nullable columns added to existing tables
    are picked up here via a simple additive ALTER TABLE check - existing
    data is never dropped or rewritten.
    """
    from app import models  # noqa: F401 - ensure models are registered
    Base.metadata.create_all(bind=get_engine())
    _apply_additive_column_migrations()


def _apply_additive_column_migrations() -> None:
    from sqlalchemy import inspect, text

    engine = get_engine()
    inspector = inspect(engine)
    if "comparisons" not in inspector.get_table_names():
        return
    existing_columns = {c["name"] for c in inspector.get_columns("comparisons")}
    additive_columns = {
        "source_label": "VARCHAR(255)",
        "destination_label": "VARCHAR(255)",
        "error_message": "TEXT",
        "duration": "FLOAT",
    }
    missing = {name: ddl for name, ddl in additive_columns.items() if name not in existing_columns}
    if not missing:
        return
    with engine.begin() as conn:
        for name, ddl in missing.items():
            conn.execute(text(f"ALTER TABLE comparisons ADD COLUMN {name} {ddl}"))


def get_db() -> Iterator[Session]:
    """FastAPI dependency."""
    SessionLocal = get_sessionmaker()
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


@contextmanager
def session_scope() -> Iterator[Session]:
    """Context manager for use outside of FastAPI (CLI, scripts, tests)."""
    SessionLocal = get_sessionmaker()
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()
