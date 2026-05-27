"""Report endpoint tests (need real DB + seed)."""
from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import needs_db


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@needs_db
def test_csv_report_requires_manager(client: TestClient, operator_token: str) -> None:
    resp = client.get("/reports/energy.csv", headers=_auth(operator_token))
    assert resp.status_code == 403


@needs_db
def test_csv_report_manager_ok(client: TestClient, manager_token: str) -> None:
    resp = client.get("/reports/energy.csv", headers=_auth(manager_token))
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert "asset_name,asset_type,energy_kwh,avg_power_kw" in resp.text


@needs_db
def test_pdf_report_manager_ok(client: TestClient, manager_token: str) -> None:
    resp = client.get("/reports/energy.pdf", headers=_auth(manager_token))
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")
