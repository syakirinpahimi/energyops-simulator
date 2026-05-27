"""Auth integration tests (need real DB + seed)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import needs_db


@needs_db
def test_login_success_and_me(client: TestClient) -> None:
    resp = client.post(
        "/auth/login",
        json={"email": "operator@energyops.local", "password": "Operator#12345"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    token = body["access_token"]
    assert body["user"]["role"] == "operator"

    me = client.get("/auth/me", headers={"Authorization": f"Bearer {token}"})
    assert me.status_code == 200
    assert me.json()["email"] == "operator@energyops.local"


@needs_db
def test_login_invalid_credentials(client: TestClient) -> None:
    resp = client.post(
        "/auth/login",
        json={"email": "operator@energyops.local", "password": "wrong"},
    )
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "INVALID_CREDENTIALS"


def test_me_requires_token(client: TestClient) -> None:
    resp = client.get("/auth/me")
    assert resp.status_code == 401


@needs_db
def test_versioned_route_alias(client: TestClient) -> None:
    """The /api/v1/* mirror should accept the same login."""
    from app.config import settings

    resp = client.post(
        "/api/v1/auth/login",
        json={"email": settings.seed_admin_email, "password": settings.seed_admin_password},
    )
    assert resp.status_code == 200
