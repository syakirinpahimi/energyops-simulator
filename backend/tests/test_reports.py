"""Report endpoint + service tests.

Tests fall into three buckets:

- **Pure-Python guards** for the empty-asset and zero-window paths. These
  short-circuit before any DB I/O, so they always run.
- **Service tests** against a real Postgres+TimescaleDB session. They
  insert rows inside a savepoint and roll back, so they don't pollute the
  seeded data.
- **HTTP smoke tests** that exercise the FastAPI routes end-to-end.

The service / HTTP tests are gated behind ``needs_db`` (the same gate
used elsewhere in the suite) so a laptop without docker compose still
gets a green run.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock
from uuid import uuid4

import pytest
from fastapi.testclient import TestClient

from app.db import SessionLocal
from app.models import Alarm, Area, Asset, Company, Sensor, Site, Telemetry
from app.services.report_service import (
    compute_alarm_summary,
    compute_energy_summary,
)
from tests.conftest import DB_AVAILABLE, needs_db


# ---------------------------------------------------------------------------
# Pure-Python tests (no DB required)
# ---------------------------------------------------------------------------


def test_energy_summary_no_assets_returns_zero():
    """Empty asset list short-circuits before touching the DB."""
    db = MagicMock()
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(hours=1)

    summary = compute_energy_summary(db, [], start, end)

    assert summary.total_kwh == 0.0
    assert summary.peak_kw == 0.0
    assert summary.per_asset == []
    assert summary.asset_count == 0
    db.execute.assert_not_called()


def test_energy_summary_zero_window_returns_zero():
    """Zero-length windows return zero without querying telemetry."""
    db = MagicMock()
    fake_asset = MagicMock(id=uuid4(), name="x", asset_type="meter")
    instant = datetime(2026, 1, 1, tzinfo=timezone.utc)

    summary = compute_energy_summary(db, [fake_asset], instant, instant)
    assert summary.total_kwh == 0.0
    assert summary.peak_kw == 0.0
    db.execute.assert_not_called()


def test_alarm_summary_no_assets_returns_zero():
    db = MagicMock()
    start = datetime(2026, 1, 1, tzinfo=timezone.utc)
    end = start + timedelta(hours=1)

    summary = compute_alarm_summary(db, [], start, end)

    assert summary.total == 0
    assert summary.by_status == {"active": 0, "acknowledged": 0, "resolved": 0}
    assert summary.by_severity == {"info": 0, "warning": 0, "critical": 0}
    db.execute.assert_not_called()


# ---------------------------------------------------------------------------
# Service tests against the real DB (needs Postgres + Timescale)
# ---------------------------------------------------------------------------


@pytest.fixture()
def scratch_session():
    """Session that rolls back everything on teardown.

    Uses a SAVEPOINT-style nested transaction so the test can ``flush``
    freely; the outer transaction is rolled back, leaving the seeded data
    untouched.
    """
    if not DB_AVAILABLE:
        pytest.skip("DB not reachable; service tests need Postgres + Timescale")
    db = SessionLocal()
    try:
        db.begin_nested()
        yield db
    finally:
        db.rollback()
        db.close()


def _make_scratch_assets(db) -> dict:
    """Create a throw-away company / site / area / 2 assets with sensors.

    The slugs include a UUID4 hex prefix so concurrent test runs don't
    collide on the unique constraints.
    """
    tag = uuid4().hex[:8]
    company = Company(slug=f"acme-{tag}", name=f"Acme {tag}")
    db.add(company)
    db.flush()

    site = Site(company_id=company.id, slug=f"site-{tag}", name=f"Site {tag}")
    db.add(site)
    db.flush()
    area = Area(site_id=site.id, slug=f"area-{tag}", name=f"Area {tag}")
    db.add(area)
    db.flush()

    boiler = Asset(
        area_id=area.id,
        slug=f"boiler-{tag}",
        name=f"Boiler {tag}",
        asset_type="boiler",
        status="online",
    )
    meter = Asset(
        area_id=area.id,
        slug=f"meter-{tag}",
        name=f"Meter {tag}",
        asset_type="meter",
        status="online",
    )
    db.add_all([boiler, meter])
    db.flush()

    s_power = Sensor(asset_id=boiler.id, metric="power_kw", unit="kW")
    s_energy = Sensor(asset_id=meter.id, metric="energy_kwh", unit="kWh")
    db.add_all([s_power, s_energy])
    db.flush()

    return {
        "company": company,
        "site": site,
        "area": area,
        "boiler": boiler,
        "meter": meter,
        "s_power": s_power,
        "s_energy": s_energy,
    }


def _add_telemetry(db, *, asset, sensor, metric, samples, company_id, site_id, area_id):
    rows = [
        Telemetry(
            ts=ts,
            company_id=company_id,
            site_id=site_id,
            area_id=area_id,
            asset_id=asset.id,
            sensor_id=sensor.id,
            metric=metric,
            value=value,
            unit=sensor.unit,
            quality="good",
        )
        for ts, value in samples
    ]
    db.add_all(rows)
    db.flush()


@needs_db
def test_energy_summary_uses_meter_max_minus_min(scratch_session):
    """Cumulative energy_kwh consumption is max(value) - min(value)."""
    seed = _make_scratch_assets(scratch_session)
    start = datetime(2026, 6, 1, tzinfo=timezone.utc)
    end = start + timedelta(hours=2)

    _add_telemetry(
        scratch_session,
        asset=seed["meter"],
        sensor=seed["s_energy"],
        metric="energy_kwh",
        samples=[
            (start, 1000.0),
            (start + timedelta(minutes=30), 1010.0),
            (start + timedelta(minutes=60), 1025.0),
            (start + timedelta(minutes=119), 1042.5),
        ],
        company_id=seed["company"].id,
        site_id=seed["site"].id,
        area_id=seed["area"].id,
    )

    summary = compute_energy_summary(
        scratch_session, [seed["boiler"], seed["meter"]], start, end
    )
    rows = {a.asset_id: a for a in summary.per_asset}
    assert rows[seed["meter"].id].energy_kwh == pytest.approx(42.5)
    assert summary.total_kwh == pytest.approx(42.5)


@needs_db
def test_energy_summary_falls_back_to_power_integration(scratch_session):
    """Assets without an energy meter still contribute via avg power * hours."""
    seed = _make_scratch_assets(scratch_session)
    start = datetime(2026, 6, 2, tzinfo=timezone.utc)
    end = start + timedelta(hours=2)

    _add_telemetry(
        scratch_session,
        asset=seed["boiler"],
        sensor=seed["s_power"],
        metric="power_kw",
        samples=[
            (start, 100.0),
            (start + timedelta(minutes=30), 200.0),
        ],
        company_id=seed["company"].id,
        site_id=seed["site"].id,
        area_id=seed["area"].id,
    )

    summary = compute_energy_summary(scratch_session, [seed["boiler"]], start, end)
    boiler_row = summary.per_asset[0]
    assert boiler_row.avg_power_kw == pytest.approx(150.0)
    assert boiler_row.peak_kw == pytest.approx(200.0)
    # avg(150 kW) * 2 hours = 300 kWh
    assert boiler_row.energy_kwh == pytest.approx(300.0)
    assert summary.peak_kw == pytest.approx(200.0)


@needs_db
def test_energy_summary_handles_sparse_data(scratch_session):
    """Missing telemetry across all assets must coalesce to zero."""
    seed = _make_scratch_assets(scratch_session)
    start = datetime(2026, 6, 3, tzinfo=timezone.utc)
    end = start + timedelta(hours=1)

    summary = compute_energy_summary(
        scratch_session, [seed["boiler"], seed["meter"]], start, end
    )

    assert summary.total_kwh == 0.0
    assert summary.peak_kw == 0.0
    assert all(row.energy_kwh == 0.0 for row in summary.per_asset)


@needs_db
def test_alarm_summary_groups_by_status_and_severity(scratch_session):
    seed = _make_scratch_assets(scratch_session)
    start = datetime(2026, 6, 4, tzinfo=timezone.utc)
    end = start + timedelta(days=1)

    scratch_session.add_all(
        [
            Alarm(
                site_id=seed["site"].id,
                asset_id=seed["boiler"].id,
                code="TEMP_HIGH",
                severity="critical",
                state="OPEN",
                message="hot",
                opened_at=start + timedelta(minutes=10),
            ),
            Alarm(
                site_id=seed["site"].id,
                asset_id=seed["boiler"].id,
                code="VIB_HIGH",
                severity="warning",
                state="ACK",
                message="shake",
                opened_at=start + timedelta(minutes=20),
            ),
            Alarm(
                site_id=seed["site"].id,
                asset_id=seed["meter"].id,
                code="POWER_LOST",
                severity="info",
                state="RESOLVED",
                message="ok",
                opened_at=start + timedelta(minutes=30),
            ),
        ]
    )
    scratch_session.flush()

    alarms = compute_alarm_summary(
        scratch_session, [seed["boiler"], seed["meter"]], start, end
    )
    assert alarms.total == 3
    assert alarms.by_status == {"active": 1, "acknowledged": 1, "resolved": 1}
    assert alarms.by_severity == {"info": 1, "warning": 1, "critical": 1}


@needs_db
def test_alarm_summary_filtered_by_asset_set(scratch_session):
    """Alarms outside the supplied asset list are excluded."""
    seed = _make_scratch_assets(scratch_session)
    start = datetime(2026, 6, 5, tzinfo=timezone.utc)
    end = start + timedelta(days=1)

    scratch_session.add_all(
        [
            Alarm(
                site_id=seed["site"].id,
                asset_id=seed["boiler"].id,
                code="TEMP_HIGH",
                severity="critical",
                state="OPEN",
                message="hot",
                opened_at=start + timedelta(minutes=10),
            ),
            Alarm(
                site_id=seed["site"].id,
                asset_id=seed["meter"].id,
                code="POWER_LOST",
                severity="info",
                state="OPEN",
                message="ok",
                opened_at=start + timedelta(minutes=30),
            ),
        ]
    )
    scratch_session.flush()

    alarms = compute_alarm_summary(scratch_session, [seed["boiler"]], start, end)

    assert alarms.total == 1
    assert alarms.by_severity["critical"] == 1
    assert alarms.by_severity["info"] == 0


# ---------------------------------------------------------------------------
# HTTP smoke tests (needs the full seeded DB)
# ---------------------------------------------------------------------------


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


@needs_db
def test_summary_requires_manager(client: TestClient, operator_token: str) -> None:
    resp = client.get("/reports/energy/summary", headers=_auth(operator_token))
    assert resp.status_code == 403


@needs_db
def test_summary_manager_ok(client: TestClient, manager_token: str) -> None:
    resp = client.get("/reports/energy/summary", headers=_auth(manager_token))
    assert resp.status_code == 200
    body = resp.json()
    for key in ("total_kwh", "peak_kw", "top_assets", "alarms", "duration_hours"):
        assert key in body
    assert "by_severity" in body["alarms"]
    assert "by_status" in body["alarms"]


@needs_db
def test_csv_report_requires_manager(client: TestClient, operator_token: str) -> None:
    resp = client.get("/reports/energy.csv", headers=_auth(operator_token))
    assert resp.status_code == 403


@needs_db
def test_csv_report_manager_ok(client: TestClient, manager_token: str) -> None:
    resp = client.get("/reports/energy.csv", headers=_auth(manager_token))
    assert resp.status_code == 200
    assert resp.headers["content-type"].startswith("text/csv")
    assert resp.text.splitlines()[0] == (
        "timestamp,site,area,asset,sensor,metric,value,unit,quality"
    )


@needs_db
def test_csv_report_filtered_by_site(client: TestClient, manager_token: str) -> None:
    """Site filter must reduce the row count vs the unfiltered call."""
    sites = client.get("/sites", headers=_auth(manager_token)).json()
    if not sites:
        pytest.skip("no seeded sites")
    site_id = sites[0]["id"]
    full = client.get("/reports/energy.csv", headers=_auth(manager_token))
    filtered = client.get(
        f"/reports/energy.csv?site_id={site_id}", headers=_auth(manager_token)
    )
    assert full.status_code == 200 and filtered.status_code == 200
    assert len(filtered.text.splitlines()) <= len(full.text.splitlines())


@needs_db
def test_pdf_report_manager_ok(client: TestClient, manager_token: str) -> None:
    resp = client.get("/reports/energy.pdf", headers=_auth(manager_token))
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")
