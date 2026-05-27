"""Tests that run without a database.

Validates the FastAPI app boots and /health degrades gracefully.
"""
from __future__ import annotations

from fastapi.testclient import TestClient


def test_app_imports_and_health(client: TestClient) -> None:
    resp = client.get("/health")
    assert resp.status_code == 200
    body = resp.json()
    assert body["status"] in {"ok", "degraded"}
    assert body["db"] in {"up", "down"}
    assert "version" in body


def test_login_requires_db_or_returns_503(client: TestClient) -> None:
    """Without a real DB, login surfaces a clean 5xx, not a stack trace."""
    resp = client.post(
        "/auth/login",
        json={"email": "nobody@example.com", "password": "x"},
    )
    # When the DB is reachable but the user doesn't exist -> 401.
    # When the DB isn't reachable -> 503 from the OperationalError handler.
    assert resp.status_code in {401, 503}
    body = resp.json()
    assert "error" in body and "code" in body["error"]


def test_unauthenticated_endpoints_return_401(client: TestClient) -> None:
    for path in [
        "/auth/me",
        "/companies",
        "/sites",
        "/areas",
        "/assets",
        "/sensors",
        "/telemetry/latest",
        "/alarms",
        "/audit-log",
    ]:
        resp = client.get(path)
        assert resp.status_code in {401, 422, 503}, f"{path}: {resp.status_code}"


def test_openapi_schema_loads(client: TestClient) -> None:
    resp = client.get("/openapi.json")
    assert resp.status_code == 200
    paths = resp.json()["paths"]
    expected = [
        "/health",
        "/auth/login",
        "/auth/me",
        "/companies",
        "/sites",
        "/areas",
        "/assets",
        "/sensors",
        "/telemetry/latest",
        "/telemetry/history",
        "/alarms",
        "/alarms/{alarm_id}/acknowledge",
        "/reports/energy.csv",
        "/reports/energy.pdf",
        "/audit-log",
    ]
    for p in expected:
        assert p in paths, f"missing path: {p}"
