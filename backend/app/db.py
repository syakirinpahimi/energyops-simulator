"""Database engine + session factory.

Kept deliberately small. Other backend tracks (auth, routers, MQTT) import
`SessionLocal` and `engine` from here.

This module owns:
  - the SQLAlchemy `engine`
  - the `SessionLocal` factory
  - the declarative `Base` class

It does NOT own model definitions � those live in `app/models.py`.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, Session, sessionmaker

from app.config import settings


class Base(DeclarativeBase):
    """Common SQLAlchemy declarative base for all ORM models."""


# `pool_pre_ping` avoids stale-connection errors after the DB restarts.
engine = create_engine(
    settings.sync_database_url,
    pool_pre_ping=True,
    future=True,
)

SessionLocal = sessionmaker(
    bind=engine,
    autoflush=False,
    autocommit=False,
    expire_on_commit=False,
    future=True,
)


def get_session():
    """FastAPI dependency: yields a transactional session.

    Other backend tracks can import this from `app.db`.
    """
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# Alias used by routers written against `Depends(get_db)`.
get_db = get_session


@contextmanager
def session_scope():
    """Context-managed Session for non-request code (seed scripts, tests)."""
    db = SessionLocal()
    try:
        yield db
        db.commit()
    except Exception:
        db.rollback()
        raise
    finally:
        db.close()


def init_db_tables() -> None:
    """Create all tables if they do not exist.

    Postgres production should rely on Alembic migrations, but tests and
    first-run convenience use this. Imports models lazily to avoid cycles.
    """
    from app import models  # noqa: F401

    Base.metadata.create_all(bind=engine)


def ping_db() -> bool:
    """Return True if the DB is reachable. Used by /health."""
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False

