"""Pytest fixtures.

Strategy mirrors ``tests/db/test_smoke.py``: integration tests that need a
real database are skipped when one is not reachable, so a plain ``pytest``
run on a junior's laptop without docker compose stays green.

Set ``RUN_DB_TESTS=1`` after running the seed once (``python -m
scripts.reset_db --seed``) to force the heavier suites to run.

Tests that don't need the DB (e.g. /health when DB is missing) live in
``tests/test_smoke_app.py`` and run unconditionally.
"""
from __future__ import annotations

import os

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text
from sqlalchemy.exc import OperationalError, SQLAlchemyError

from app.config import settings
from app.db import SessionLocal


def _db_reachable() -> bool:
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        return True
    except (OperationalError, SQLAlchemyError):
        return False
    except Exception:
        return False


DB_AVAILABLE = os.environ.get("RUN_DB_TESTS") == "1" or _db_reachable()


needs_db = pytest.mark.skipif(
    not DB_AVAILABLE,
    reason="DB not reachable; start postgres + run `python -m scripts.reset_db --seed` or set RUN_DB_TESTS=1",
)


@pytest.fixture()
def client() -> TestClient:
    from app.main import app

    return TestClient(app)


def _login_token(client: TestClient, email: str, password: str) -> str:
    resp = client.post("/auth/login", json={"email": email, "password": password})
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


@pytest.fixture()
def operator_token(client: TestClient) -> str:
    return _login_token(
        client, settings.seed_operator_email, settings.seed_operator_password
    )


@pytest.fixture()
def manager_token(client: TestClient) -> str:
    return _login_token(
        client, settings.seed_manager_email, settings.seed_manager_password
    )


@pytest.fixture()
def engineer_token(client: TestClient) -> str:
    return _login_token(
        client, settings.seed_engineer_email, settings.seed_engineer_password
    )
