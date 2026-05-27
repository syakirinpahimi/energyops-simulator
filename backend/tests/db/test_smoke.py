"""DB smoke test.

Runs only when a real database is reachable. Skipped otherwise so a junior
running `pytest` without docker compose up still gets a green run.

What it asserts (after seed):
  * the demo company exists
  * all 3 sites exist
  * all 5 expected assets exist
  * each asset has at least one sensor
  * the 4 demo users exist with the expected roles
  * `telemetry` is registered as a Timescale hypertable
"""
from __future__ import annotations

import os
import sys
from pathlib import Path

import pytest
from sqlalchemy import select, text
from sqlalchemy.exc import OperationalError

# Make `app.*` imports resolvable without needing an installed package.
ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.db import SessionLocal  # noqa: E402
from app.models import Asset, Company, Sensor, Site, User  # noqa: E402


EXPECTED_SITE_SLUGS = {"kuantan-plant", "johor-solar-farm", "kl-data-centre"}

EXPECTED_ASSET_SLUGS = {"p-101", "c-201", "ch-1", "inv-01", "gm-01"}

EXPECTED_USER_ROLES = {"operator", "engineer", "manager", "admin"}


def _db_reachable() -> bool:
    try:
        with SessionLocal() as db:
            db.execute(text("SELECT 1"))
        return True
    except OperationalError:
        return False


pytestmark = pytest.mark.skipif(
    os.environ.get("RUN_DB_TESTS") != "1" and not _db_reachable(),
    reason="DB not reachable; set RUN_DB_TESTS=1 after `python -m scripts.reset_db --seed`",
)


def test_demo_company_exists():
    with SessionLocal() as db:
        company = db.scalar(
            select(Company).where(Company.slug == "demo-industrial")
        )
        assert company is not None, "seed not run? expected demo-industrial company"
        assert company.name == "Demo Industrial Holdings"


def test_all_sites_seeded():
    with SessionLocal() as db:
        slugs = set(db.scalars(select(Site.slug)).all())
        missing = EXPECTED_SITE_SLUGS - slugs
        assert not missing, f"missing sites: {missing}"


def test_all_assets_seeded():
    with SessionLocal() as db:
        slugs = set(db.scalars(select(Asset.slug)).all())
        missing = EXPECTED_ASSET_SLUGS - slugs
        assert not missing, f"missing assets: {missing}"


def test_each_asset_has_sensors():
    with SessionLocal() as db:
        for slug in EXPECTED_ASSET_SLUGS:
            asset = db.scalar(select(Asset).where(Asset.slug == slug))
            assert asset is not None, f"asset {slug} not found"
            sensor_count = db.scalar(
                select(text("count(*)"))
                .select_from(Sensor.__table__)
                .where(Sensor.asset_id == asset.id)
            )
            assert sensor_count and sensor_count > 0, (
                f"asset {slug} has no sensors"
            )


def test_demo_users_present():
    with SessionLocal() as db:
        roles = set(db.scalars(select(User.role)).all())
        missing = EXPECTED_USER_ROLES - {str(r) for r in roles}
        assert not missing, f"missing user roles: {missing}"


def test_telemetry_is_hypertable():
    with SessionLocal() as db:
        row = db.execute(
            text(
                "SELECT 1 FROM timescaledb_information.hypertables "
                "WHERE hypertable_name = 'telemetry'"
            )
        ).first()
        assert row is not None, "telemetry is not registered as a hypertable"
