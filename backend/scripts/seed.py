"""Seed the demo database.

Run with:

    python -m scripts.seed                  # from backend/
    docker compose exec backend python -m scripts.seed

Idempotent at the company level: if the demo company already exists the
script logs a notice and exits. To rebuild from scratch use:

    python -m scripts.reset_db --seed

What it creates:
  * 1 company:  Demo Industrial Holdings
  * 3 sites:    Kuantan Plant, Johor Solar Farm, KL Data Centre
  * 5 areas (across the sites)
  * 5 assets (one per asset spec in the data-track prompt)
  * sensors per asset, drawn from the canonical metric list
  * 4 demo users, one per role, with bcrypt-hashed passwords

Telemetry backfill is intentionally NOT done here � the simulator track
owns realistic time-series generation. We just give the schema enough
shape that dashboards have something to render.
"""
from __future__ import annotations

import logging
import sys
from pathlib import Path

# Make `app.*` imports work whether invoked as a module or directly.
ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models import (
    Alarm,
    Area,
    Asset,
    AuditLog,
    Company,
    Sensor,
    Site,
    User,
)
from app.security import hash_password


log = logging.getLogger("seed")


# ---------------------------------------------------------------------------
# Static seed data � edit here if the demo set ever changes.
# ---------------------------------------------------------------------------

COMPANY = {"slug": "demo-industrial", "name": "Demo Industrial Holdings"}

SITES = [
    {
        "slug": "kuantan-plant",
        "name": "Kuantan Plant",
        "timezone": "Asia/Kuala_Lumpur",
        "location": {"lat": 3.8077, "lon": 103.3260, "address": "Kuantan, Pahang"},
    },
    {
        "slug": "johor-solar-farm",
        "name": "Johor Solar Farm",
        "timezone": "Asia/Kuala_Lumpur",
        "location": {"lat": 1.4927, "lon": 103.7414, "address": "Iskandar Puteri, Johor"},
    },
    {
        "slug": "kl-data-centre",
        "name": "KL Data Centre",
        "timezone": "Asia/Kuala_Lumpur",
        "location": {"lat": 3.1390, "lon": 101.6869, "address": "Kuala Lumpur"},
    },
]

# (site_slug, area_slug, area_name)
AREAS = [
    ("kuantan-plant",    "production-line-a",  "Production Line A"),
    ("kuantan-plant",    "utilities",          "Utilities"),
    ("kuantan-plant",    "pump-house",         "Pump House"),
    ("johor-solar-farm", "solar-inverter-field", "Solar Inverter Field"),
    ("kl-data-centre",   "chiller-plant",      "Chiller Plant"),
]

# Sensor templates by asset_type. Order is the order the seeder creates them.
SENSORS_BY_TYPE: dict[str, list[tuple[str, str, str]]] = {
    # asset_type: [(metric, unit, description), ...]
    "pump": [
        ("power_kw",      "kW",   "Active power draw"),
        ("current_a",     "A",    "Phase current"),
        ("flow_m3_h",     "m�/h", "Outlet flow rate"),
        ("pressure_bar",  "bar",  "Discharge pressure"),
        ("vibration_mm_s", "mm/s", "Bearing vibration RMS"),
    ],
    "compressor": [
        ("power_kw",      "kW",   "Active power draw"),
        ("current_a",     "A",    "Phase current"),
        ("pressure_bar",  "bar",  "Output pressure"),
        ("temperature_c", "�C",   "Discharge temperature"),
        ("vibration_mm_s", "mm/s", "Casing vibration RMS"),
    ],
    "chiller": [
        ("power_kw",      "kW",   "Active power draw"),
        ("current_a",     "A",    "Phase current"),
        ("temperature_c", "�C",   "Supply water temperature"),
        ("flow_m3_h",     "m�/h", "Chilled water flow"),
    ],
    "inverter": [
        ("power_kw",      "kW",   "AC output power"),
        ("voltage_v",     "V",    "DC bus voltage"),
        ("current_a",     "A",    "AC output current"),
        ("temperature_c", "�C",   "Heatsink temperature"),
    ],
    "meter": [
        ("power_kw",      "kW",   "Total active power"),
        ("energy_kwh",    "kWh",  "Cumulative energy"),
        ("voltage_v",     "V",    "Line voltage"),
        ("current_a",     "A",    "Line current"),
    ],
}

# (site_slug, area_slug, asset_slug, asset_name, asset_type, rated_kw)
ASSETS = [
    ("kuantan-plant",    "pump-house",           "p-101",  "Pump P-101",            "pump",       55.0),
    ("kuantan-plant",    "utilities",            "c-201",  "Air Compressor C-201",  "compressor", 90.0),
    ("kl-data-centre",   "chiller-plant",        "ch-1",   "HVAC Chiller CH-1",     "chiller",    250.0),
    ("johor-solar-farm", "solar-inverter-field", "inv-01", "Solar Inverter INV-01", "inverter",   100.0),
    ("kuantan-plant",    "utilities",            "gm-01",  "Main Grid Meter GM-01", "meter",      None),
]


# ---------------------------------------------------------------------------
# Seeding logic
# ---------------------------------------------------------------------------


def _users_to_seed() -> list[dict]:
    """Build the demo user list from settings."""
    return [
        {"email": settings.seed_operator_email, "password": settings.seed_operator_password, "role": "operator", "name": "Demo Operator"},
        {"email": settings.seed_engineer_email, "password": settings.seed_engineer_password, "role": "engineer", "name": "Demo Engineer"},
        {"email": settings.seed_manager_email,  "password": settings.seed_manager_password,  "role": "manager",  "name": "Demo Manager"},
        {"email": settings.seed_admin_email,    "password": settings.seed_admin_password,    "role": "admin",    "name": "Demo Admin"},
    ]


def _seed_company(db: Session) -> Company:
    company = db.scalar(select(Company).where(Company.slug == COMPANY["slug"]))
    if company:
        log.info("company '%s' exists; skipping creation", COMPANY["slug"])
        return company
    company = Company(slug=COMPANY["slug"], name=COMPANY["name"])
    db.add(company)
    db.flush()
    log.info("created company %s", company.slug)
    return company


def _seed_sites(db: Session, company: Company) -> dict[str, Site]:
    out: dict[str, Site] = {}
    for spec in SITES:
        site = db.scalar(
            select(Site).where(
                Site.company_id == company.id, Site.slug == spec["slug"]
            )
        )
        if not site:
            site = Site(
                company_id=company.id,
                slug=spec["slug"],
                name=spec["name"],
                timezone=spec["timezone"],
                location=spec["location"],
            )
            db.add(site)
            db.flush()
            log.info("created site %s", site.slug)
        out[site.slug] = site
    return out


def _seed_areas(db: Session, sites: dict[str, Site]) -> dict[tuple[str, str], Area]:
    out: dict[tuple[str, str], Area] = {}
    for site_slug, area_slug, area_name in AREAS:
        site = sites[site_slug]
        area = db.scalar(
            select(Area).where(Area.site_id == site.id, Area.slug == area_slug)
        )
        if not area:
            area = Area(site_id=site.id, slug=area_slug, name=area_name)
            db.add(area)
            db.flush()
            log.info("created area %s/%s", site_slug, area_slug)
        out[(site_slug, area_slug)] = area
    return out


def _seed_assets_and_sensors(
    db: Session,
    sites: dict[str, Site],
    areas: dict[tuple[str, str], Area],
) -> list[Asset]:
    created: list[Asset] = []
    for site_slug, area_slug, asset_slug, asset_name, asset_type, rated_kw in ASSETS:
        area = areas[(site_slug, area_slug)]
        asset = db.scalar(
            select(Asset).where(Asset.area_id == area.id, Asset.slug == asset_slug)
        )
        if not asset:
            asset = Asset(
                area_id=area.id,
                slug=asset_slug,
                name=asset_name,
                asset_type=asset_type,
                status="offline",
                rated_power_kw=rated_kw,
                metadata_json={"site_slug": site_slug, "seeded": True},
            )
            db.add(asset)
            db.flush()
            log.info("created asset %s (%s)", asset.slug, asset.asset_type)
        created.append(asset)

        # Sensors are deterministic per asset_type. Idempotent.
        for metric, unit, description in SENSORS_BY_TYPE.get(asset_type, []):
            existing = db.scalar(
                select(Sensor).where(
                    Sensor.asset_id == asset.id, Sensor.metric == metric
                )
            )
            if existing:
                continue
            db.add(
                Sensor(
                    asset_id=asset.id,
                    metric=metric,
                    unit=unit,
                    description=description,
                )
            )
        db.flush()
    return created


def _seed_users(db: Session, company: Company) -> list[User]:
    created: list[User] = []
    for spec in _users_to_seed():
        existing = db.scalar(
            select(User).where(User.email == spec["email"])
        )
        if existing:
            continue
        user = User(
            company_id=company.id,
            email=spec["email"],
            name=spec["name"],
            password_hash=hash_password(spec["password"]),
            role=spec["role"],
            is_active=True,
        )
        db.add(user)
        created.append(user)
        log.info("created user %s (%s)", user.email, user.role)
    db.flush()
    return created


def _seed_demo_alarm(db: Session, assets: list[Asset]) -> None:
    """One example OPEN alarm so the alarms page renders something.

    Targets the pump asset to match the recruiter demo script
    ("operator detects pump anomaly"). Skipped if any alarm row
    already exists - we don't want to spam duplicate examples on
    repeated runs.
    """
    if db.scalar(select(Alarm.id).limit(1)):
        return
    target = next((a for a in assets if a.asset_type == "pump"), None)
    if target is None:
        return
    sensor = db.scalar(
        select(Sensor).where(
            Sensor.asset_id == target.id, Sensor.metric == "vibration_mm_s"
        )
    )
    db.add(
        Alarm(
            site_id=db.scalar(
                select(Area.site_id).where(Area.id == target.area_id)
            ),
            asset_id=target.id,
            sensor_id=sensor.id if sensor else None,
            code="VIBRATION_HIGH",
            severity="warning",
            state="OPEN",
            message="Bearing vibration above warning threshold",
            triggered_value=8.4,
            threshold_value=8.0,
        )
    )
    log.info("created demo alarm on %s", target.slug)


def run() -> int:
    """Run the full seed. Returns the number of new top-level rows created."""
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )

    with SessionLocal() as db:  # type: Session
        try:
            company = _seed_company(db)
            sites = _seed_sites(db, company)
            areas = _seed_areas(db, sites)
            assets = _seed_assets_and_sensors(db, sites, areas)
            users = _seed_users(db, company)
            _seed_demo_alarm(db, assets)

            # One audit entry so the audit page is non-empty.
            admin = next(
                (u for u in users if u.role == "admin"), None
            ) or db.scalar(
                select(User).where(User.role == "admin").limit(1)
            )
            if admin:
                db.add(
                    AuditLog(
                        user_id=admin.id,
                        actor_email=admin.email,
                        action="seed.run",
                        entity_type="company",
                        entity_id=company.id,
                        details_json={"sites": len(sites), "assets": len(assets)},
                    )
                )

            db.commit()
            log.info(
                "seed complete: %d sites, %d areas, %d assets, %d users",
                len(sites),
                len(areas),
                len(assets),
                len(users),
            )
            return len(assets)
        except Exception:
            db.rollback()
            log.exception("seed failed; rolled back")
            raise


if __name__ == "__main__":  # pragma: no cover
    run()
