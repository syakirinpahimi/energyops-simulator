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
from sqlalchemy import delete, select

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


# A sentinel window in the far future so the rows we insert here can't
# clash with real seeded telemetry or anything the simulator track might
# leave behind. Used by the report HTTP tests below; cleaned up in the
# fixture teardown.
_REPORT_WINDOW_START = datetime(2099, 1, 1, tzinfo=timezone.utc)
_REPORT_WINDOW_END = datetime(2099, 1, 2, tzinfo=timezone.utc)


@pytest.fixture()
def seeded_report_window():
    """Insert known telemetry rows under two seeded sites in 2099.

    Uses the real seeded hierarchy (the same one the HTTP layer sees) so
    the report endpoint returns rows without any monkeypatching. The
    rows are committed so the FastAPI ``TestClient`` can read them
    through its own session, and removed in teardown so subsequent
    tests start clean.

    Returns a dict describing the two sites we wrote rows for plus the
    ISO-formatted window bounds.
    """
    if not DB_AVAILABLE:
        pytest.skip("DB not reachable; report HTTP tests need Postgres + Timescale")
    db = SessionLocal()
    try:
        sites = list(db.scalars(select(Site).order_by(Site.name)))
        if len(sites) < 2:
            pytest.skip("need at least two seeded sites for site-filter test")
        site_a, site_b = sites[0], sites[1]

        def _first_asset(site_id):
            return db.scalar(
                select(Asset)
                .join(Area, Area.id == Asset.area_id)
                .where(Area.site_id == site_id)
                .order_by(Asset.name)
            )

        asset_a = _first_asset(site_a.id)
        asset_b = _first_asset(site_b.id)
        if asset_a is None or asset_b is None:
            pytest.skip("seed missing assets under both sites")

        sensor_a = db.scalar(
            select(Sensor).where(Sensor.asset_id == asset_a.id).order_by(Sensor.metric)
        )
        sensor_b = db.scalar(
            select(Sensor).where(Sensor.asset_id == asset_b.id).order_by(Sensor.metric)
        )
        if sensor_a is None or sensor_b is None:
            pytest.skip("seed missing sensors under both sites")

        company_id = db.scalar(select(Site.company_id).where(Site.id == site_a.id))

        rows = []
        for i, (asset, sensor, site) in enumerate(
            [
                (asset_a, sensor_a, site_a),
                (asset_a, sensor_a, site_a),
                (asset_a, sensor_a, site_a),
                (asset_b, sensor_b, site_b),
                (asset_b, sensor_b, site_b),
            ]
        ):
            rows.append(
                Telemetry(
                    ts=_REPORT_WINDOW_START + timedelta(minutes=i),
                    company_id=company_id,
                    site_id=site.id,
                    area_id=asset.area_id,
                    asset_id=asset.id,
                    sensor_id=sensor.id,
                    metric=sensor.metric,
                    value=10.0 + i,
                    unit=sensor.unit,
                    quality="good",
                )
            )
        db.add_all(rows)
        db.commit()

        yield {
            "start": _REPORT_WINDOW_START,
            "end": _REPORT_WINDOW_END,
            # Use the trailing-Z form so the timestamps survive being
            # spliced straight into a query string. The "+00:00" form
            # gets URL-decoded to a space and explodes Pydantic parsing
            # with a 422.
            "start_iso": "2099-01-01T00:00:00Z",
            "end_iso": "2099-01-02T00:00:00Z",
            "site_a_id": str(site_a.id),
            "site_a_name": site_a.name,
            "site_b_id": str(site_b.id),
            "site_b_name": site_b.name,
            "rows_a": 3,
            "rows_b": 2,
        }
    finally:
        db.execute(
            delete(Telemetry).where(
                Telemetry.ts >= _REPORT_WINDOW_START,
                Telemetry.ts < _REPORT_WINDOW_END,
            )
        )
        db.commit()
        db.close()


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
def test_csv_report_filtered_by_site(
    client: TestClient, manager_token: str, seeded_report_window
) -> None:
    """Site filter must include only the chosen site's rows.

    Uses a fixture-seeded sentinel window so the assertion is exact
    (3 rows for site A, 2 rows for site B) rather than the older
    "<=" comparison that passed even when the filter did nothing.
    """
    window = seeded_report_window
    qs = f"start={window['start_iso']}&end={window['end_iso']}"

    full = client.get(f"/reports/energy.csv?{qs}", headers=_auth(manager_token))
    filtered_a = client.get(
        f"/reports/energy.csv?{qs}&site_id={window['site_a_id']}",
        headers=_auth(manager_token),
    )
    filtered_b = client.get(
        f"/reports/energy.csv?{qs}&site_id={window['site_b_id']}",
        headers=_auth(manager_token),
    )

    assert full.status_code == 200
    assert filtered_a.status_code == 200
    assert filtered_b.status_code == 200

    def _data_lines(text: str) -> list[str]:
        # Drop the header row; ignore trailing blank line from csv writer.
        return [ln for ln in text.splitlines()[1:] if ln]

    full_lines = _data_lines(full.text)
    a_lines = _data_lines(filtered_a.text)
    b_lines = _data_lines(filtered_b.text)

    assert len(a_lines) == window["rows_a"]
    assert len(b_lines) == window["rows_b"]
    assert len(full_lines) >= window["rows_a"] + window["rows_b"]

    # Every filtered row must mention the chosen site name and none of
    # the other site's name.
    assert all(window["site_a_name"] in ln for ln in a_lines)
    assert all(window["site_b_name"] not in ln for ln in a_lines)
    assert all(window["site_b_name"] in ln for ln in b_lines)
    assert all(window["site_a_name"] not in ln for ln in b_lines)


@needs_db
def test_csv_report_not_truncated_for_small_result(
    client: TestClient, manager_token: str, seeded_report_window
) -> None:
    """Small result sets advertise X-Report-Truncated: false."""
    window = seeded_report_window
    resp = client.get(
        f"/reports/energy.csv?start={window['start_iso']}&end={window['end_iso']}",
        headers=_auth(manager_token),
    )
    assert resp.status_code == 200
    assert resp.headers["x-report-truncated"] == "false"
    # Row-limit header is only set when truncation actually happened.
    assert "x-report-row-limit" not in resp.headers


@needs_db
def test_csv_report_truncated_when_over_limit(
    client: TestClient, manager_token: str, seeded_report_window, monkeypatch
) -> None:
    """When the query exceeds the cap the response advertises it.

    We monkeypatch the cap down to 2 instead of inserting 100k+ rows so
    the test runs quickly. The header contract is the same either way:
    X-Report-Truncated: true and X-Report-Row-Limit echoes the cap.
    """
    from app.routes import reports as reports_module

    monkeypatch.setattr(reports_module, "CSV_ROW_LIMIT", 2)

    window = seeded_report_window  # 5 rows total in the window
    resp = client.get(
        f"/reports/energy.csv?start={window['start_iso']}&end={window['end_iso']}",
        headers=_auth(manager_token),
    )
    assert resp.status_code == 200
    assert resp.headers["x-report-truncated"] == "true"
    assert resp.headers["x-report-row-limit"] == "2"

    # Body should contain the header + exactly the cap (2 rows).
    data_lines = [ln for ln in resp.text.splitlines()[1:] if ln]
    assert len(data_lines) == 2


@needs_db
def test_pdf_report_manager_ok(client: TestClient, manager_token: str) -> None:
    resp = client.get("/reports/energy.pdf", headers=_auth(manager_token))
    assert resp.status_code == 200
    assert resp.headers["content-type"] == "application/pdf"
    assert resp.content.startswith(b"%PDF")
