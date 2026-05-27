"""Telemetry routes: latest grouped by asset, and history with bucketing.

History uses time-bucketing in pure SQL so it works on plain Postgres
without TimescaleDB; on Timescale you can swap to ``time_bucket()`` later
without changing the response shape.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone
from typing import Dict, List, Optional, Tuple
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user
from app.models import Area, Asset, Sensor, Site, Telemetry, User
from app.schemas import AssetLatest, LatestReading, TelemetryHistory, TelemetryPoint

router = APIRouter(prefix="/telemetry", tags=["telemetry"])


_BUCKET_SECONDS: Dict[str, int] = {
    "10s": 10,
    "1m": 60,
    "5m": 300,
    "15m": 900,
    "1h": 3600,
    "1d": 86400,
}

_AGG_FUNCS = {
    "avg": func.avg,
    "min": func.min,
    "max": func.max,
    "sum": func.sum,
    "last": func.max,  # without window funcs we approximate "last" as max(value)
}


def _bad_request(code: str, message: str, **details) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail={"error": {"code": code, "message": message, "details": details}},
    )


@router.get("/latest", response_model=List[AssetLatest])
def latest_telemetry(
    site_id: Optional[UUID] = Query(default=None),
    asset_id: Optional[UUID] = Query(default=None),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> List[AssetLatest]:
    """Return the most recent reading per sensor, grouped by asset.

    Filterable by ``site_id`` or ``asset_id``. Defaults to all assets in
    the user's company.
    """
    asset_stmt = (
        select(Asset)
        .join(Area, Asset.area_id == Area.id)
        .join(Site, Area.site_id == Site.id)
        .where(Site.company_id == user.company_id)
    )
    if asset_id is not None:
        asset_stmt = asset_stmt.where(Asset.id == asset_id)
    if site_id is not None:
        asset_stmt = asset_stmt.where(Area.site_id == site_id)
    assets = list(db.scalars(asset_stmt))
    if not assets:
        return []

    asset_ids = [a.id for a in assets]
    sensors = db.scalars(select(Sensor).where(Sensor.asset_id.in_(asset_ids))).all()
    sensor_by_id = {s.id: s for s in sensors}

    # Latest ts per sensor.
    latest_per_sensor_subq = (
        select(Telemetry.sensor_id, func.max(Telemetry.ts).label("max_ts"))
        .where(Telemetry.asset_id.in_(asset_ids))
        .group_by(Telemetry.sensor_id)
        .subquery()
    )
    latest_rows = db.execute(
        select(Telemetry).join(
            latest_per_sensor_subq,
            and_(
                Telemetry.sensor_id == latest_per_sensor_subq.c.sensor_id,
                Telemetry.ts == latest_per_sensor_subq.c.max_ts,
            ),
        )
    ).scalars().all()

    readings_by_asset: Dict[UUID, List[LatestReading]] = {a.id: [] for a in assets}
    last_seen_by_asset: Dict[UUID, Optional[datetime]] = {a.id: None for a in assets}
    for row in latest_rows:
        sensor = sensor_by_id.get(row.sensor_id)
        unit = sensor.unit if sensor else ""
        readings_by_asset.setdefault(row.asset_id, []).append(
            LatestReading(
                sensor_id=row.sensor_id,
                metric=row.metric,
                unit=unit,
                value=row.value,
                ts=row.ts,
                quality=row.quality,
            )
        )
        prev = last_seen_by_asset.get(row.asset_id)
        if prev is None or row.ts > prev:
            last_seen_by_asset[row.asset_id] = row.ts

    return [
        AssetLatest(
            asset_id=a.id,
            asset_name=a.name,
            status=a.status,
            last_seen=last_seen_by_asset.get(a.id),
            readings=readings_by_asset.get(a.id, []),
        )
        for a in assets
    ]


def _parse_history_args(
    asset_id: Optional[UUID],
    sensor_id: Optional[UUID],
    metric: Optional[str],
    start: Optional[datetime],
    end: Optional[datetime],
    interval: str,
    agg: str,
) -> Tuple[datetime, datetime, int]:
    if asset_id is None and sensor_id is None:
        raise _bad_request("MISSING_TARGET", "Provide asset_id or sensor_id")
    if interval not in _BUCKET_SECONDS:
        raise _bad_request(
            "INVALID_INTERVAL",
            f"Unknown interval '{interval}'",
            allowed=list(_BUCKET_SECONDS),
        )
    if agg not in _AGG_FUNCS:
        raise _bad_request("INVALID_AGG", f"Unknown agg '{agg}'", allowed=list(_AGG_FUNCS))

    now = datetime.now(timezone.utc)
    end_ts = end or now
    start_ts = start or (end_ts - timedelta(hours=1))
    if start_ts >= end_ts:
        raise _bad_request("INVALID_RANGE", "start must be before end")
    return start_ts, end_ts, _BUCKET_SECONDS[interval]


@router.get("/history", response_model=TelemetryHistory)
def telemetry_history(
    asset_id: Optional[UUID] = Query(default=None),
    sensor_id: Optional[UUID] = Query(default=None),
    metric: Optional[str] = Query(default=None),
    start: Optional[datetime] = Query(default=None),
    end: Optional[datetime] = Query(default=None),
    interval: str = Query(default="1m"),
    agg: str = Query(default="avg"),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> TelemetryHistory:
    """Bucketed history for a sensor or asset+metric pair."""
    start_ts, end_ts, bucket_s = _parse_history_args(
        asset_id, sensor_id, metric, start, end, interval, agg
    )

    # Resolve metric/asset_id for the response and refine the WHERE clause.
    where_clauses = [Telemetry.ts >= start_ts, Telemetry.ts < end_ts]
    response_asset_id: UUID
    response_metric: str

    if sensor_id is not None:
        sensor = db.get(Sensor, sensor_id)
        if sensor is None:
            raise _bad_request("SENSOR_NOT_FOUND", "sensor_id does not exist", sensor_id=str(sensor_id))
        where_clauses.append(Telemetry.sensor_id == sensor_id)
        response_asset_id = sensor.asset_id
        response_metric = sensor.metric
    else:
        assert asset_id is not None  # narrowed by _parse_history_args
        if metric is None:
            raise _bad_request("METRIC_REQUIRED", "metric is required when querying by asset_id")
        where_clauses.append(Telemetry.asset_id == asset_id)
        where_clauses.append(Telemetry.metric == metric)
        response_asset_id = asset_id
        response_metric = metric

    # Compute bucket using floor division on epoch seconds. Works on PG + SQLite.
    epoch = func.extract("epoch", Telemetry.ts)
    bucket_epoch = (func.floor(epoch / bucket_s) * bucket_s).label("bucket_epoch")
    agg_func = _AGG_FUNCS[agg]

    stmt = (
        select(bucket_epoch, agg_func(Telemetry.value).label("v"))
        .where(and_(*where_clauses))
        .group_by(bucket_epoch)
        .order_by(bucket_epoch)
    )
    rows = db.execute(stmt).all()

    points: List[TelemetryPoint] = [
        TelemetryPoint(
            ts=datetime.fromtimestamp(float(row[0]), tz=timezone.utc),
            value=float(row[1]) if row[1] is not None else 0.0,
        )
        for row in rows
    ]

    return TelemetryHistory(
        asset_id=response_asset_id,
        metric=response_metric,
        bucket=interval,
        agg=agg,
        points=points,
    )
