"""Hierarchy + telemetry latest tests."""
from __future__ import annotations

from fastapi.testclient import TestClient

from tests.conftest import needs_db


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@needs_db
def test_companies_sites_areas_assets(client: TestClient, operator_token: str) -> None:
    h = _auth(operator_token)
    companies = client.get("/companies", headers=h).json()
    assert len(companies) == 1
    company_id = companies[0]["id"]

    sites = client.get(f"/sites?company_id={company_id}", headers=h).json()
    assert len(sites) == 3
    site_id = sites[0]["id"]

    areas = client.get(f"/areas?site_id={site_id}", headers=h).json()
    assert len(areas) >= 1
    area_id = areas[0]["id"]

    assets = client.get(f"/assets?area_id={area_id}", headers=h).json()
    assert len(assets) >= 1
    asset_id = assets[0]["id"]

    sensors = client.get(f"/assets/{asset_id}/sensors", headers=h).json()
    assert len(sensors) >= 1


@needs_db
def test_latest_telemetry_grouped_by_asset(client: TestClient, operator_token: str) -> None:
    h = _auth(operator_token)
    sites = client.get("/sites", headers=h).json()
    site_id = sites[0]["id"]

    resp = client.get(f"/telemetry/latest?site_id={site_id}", headers=h)
    assert resp.status_code == 200
    items = resp.json()
    assert isinstance(items, list)
    assert len(items) > 0
    first = items[0]
    assert "asset_id" in first and "readings" in first
    assert isinstance(first["readings"], list)


def test_latest_unauthenticated(client: TestClient) -> None:
    resp = client.get("/telemetry/latest")
    assert resp.status_code in {401, 503}
