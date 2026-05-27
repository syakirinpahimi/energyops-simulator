"""Report metric calculations backed by real telemetry.

This module owns the SQL that turns raw ``telemetry`` rows into the
numbers shown on the Reports page (cards, CSV header, PDF). It is kept
as plain functions taking a ``Session`` so route handlers and tests can
drive it the same way.

Why a separate module
---------------------
The route file used to do ``avg(power_kw) * window_hours`` inline. That
worked but was a coarse synthetic rollup. Real meters write a cumulative
``energy_kwh`` counter, so the right number is ``max(value) - min(value)``
per asset over the window. We also want the route file to stay thin and
to be exercised independently from HTTP plumbing in tests.

Approach summary
----------------
- ``total_kwh`` uses per-asset ``max(energy_kwh) - min(energy_kwh)`` where
  available, then falls back to the older ``avg(power_kw) * hours`` shape
  for assets that only emit instantaneous power.
- ``peak_kw`` is ``max(power_kw)`` across all selected telemetry.
- Top assets are ranked by computed ``energy_kwh`` (descending).
- Alarm summary is grouped by both ``severity`` and ``state`` so the UI
  and PDF can show either breakdown without a second round trip.
- All queries return zero / empty collections rather than raising when
  the window has no telemetry.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, Iterable, List, Optional, Tuple
from uuid import UUID

from sqlalchemy import and_, func, select
from sqlalchemy.orm import Session

from app.models import Alarm, Asset, Telemetry


# ---------------------------------------------------------------------------
# Public dataclasses (used by routes + tests)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class AssetEnergy:
    """Per-asset energy roll-up for the report window."""

    asset_id: UUID
    asset_name: str
    asset_type: str
    energy_kwh: float
    avg_power_kw: float
    peak_kw: float

    def as_row(self) -> Dict[str, Any]:
        return {
            "asset_id": str(self.asset_id),
            "asset_name": self.asset_name,
            "asset_type": self.asset_type,
            "energy_kwh": round(self.energy_kwh, 2),
            "avg_power_kw": round(self.avg_power_kw, 3),
            "peak_kw": round(self.peak_kw, 3),
        }


@dataclass(frozen=True)
class EnergySummary:
    """Roll-up of one report window across the selected assets."""

    start_ts: datetime
    end_ts: datetime
    duration_hours: float
    asset_count: int
    total_kwh: float
    peak_kw: float
    per_asset: List[AssetEnergy]

    def top_assets(self, limit: int = 5) -> List[AssetEnergy]:
        return sorted(self.per_asset, key=lambda a: a.energy_kwh, reverse=True)[:limit]

    def as_summary_dict(self, top_n: int = 5) -> Dict[str, Any]:
        return {
            "from": self.start_ts.isoformat(),
            "to": self.end_ts.isoformat(),
            "duration_hours": round(self.duration_hours, 3),
            "asset_count": self.asset_count,
            "total_kwh": round(self.total_kwh, 2),
            "peak_kw": round(self.peak_kw, 3),
            "top_assets": [a.as_row() for a in self.top_assets(top_n)],
        }


@dataclass(frozen=True)
class AlarmSummary:
    """Alarm counts opened in the report window."""

    by_status: Dict[str, int]      # {'active': n, 'acknowledged': n, 'resolved': n}
    by_severity: Dict[str, int]    # {'info': n, 'warning': n, 'critical': n}
    total: int

    def as_dict(self) -> Dict[str, Any]:
        return {
            **self.by_status,
            "total": self.total,
            "by_severity": dict(self.by_severity),
            "by_status": dict(self.by_status),
        }


# ---------------------------------------------------------------------------
# Energy roll-up
# ---------------------------------------------------------------------------


def _power_stats(
    db: Session,
    asset_ids: List[UUID],
    start_ts: datetime,
    end_ts: datetime,
) -> Dict[UUID, Tuple[float, float]]:
    """Return ``{asset_id: (avg_kw, max_kw)}`` for ``power_kw`` readings.

    Uses the ``idx_telemetry_asset_ts`` index. Coalesces NULL aggregates to
    0.0 so callers never have to special-case sparse windows.
    """
    if not asset_ids:
        return {}
    stmt = (
        select(
            Telemetry.asset_id,
            func.coalesce(func.avg(Telemetry.value), 0.0),
            func.coalesce(func.max(Telemetry.value), 0.0),
        )
        .where(
            and_(
                Telemetry.asset_id.in_(asset_ids),
                Telemetry.metric == "power_kw",
                Telemetry.quality != "bad",
                Telemetry.ts >= start_ts,
                Telemetry.ts < end_ts,
            )
        )
        .group_by(Telemetry.asset_id)
    )
    return {aid: (float(avg or 0.0), float(mx or 0.0)) for aid, avg, mx in db.execute(stmt).all()}


def _energy_consumption(
    db: Session,
    asset_ids: List[UUID],
    start_ts: datetime,
    end_ts: datetime,
) -> Dict[UUID, float]:
    """Return ``{asset_id: kwh}`` from cumulative ``energy_kwh`` counters.

    Energy meters emit a monotonically increasing kWh total, so the
    consumption over the window is ``max(value) - min(value)`` per asset.
    Negative results (counter rollover, bad data) are clamped to 0.
    """
    if not asset_ids:
        return {}
    stmt = (
        select(
            Telemetry.asset_id,
            func.coalesce(func.max(Telemetry.value) - func.min(Telemetry.value), 0.0),
        )
        .where(
            and_(
                Telemetry.asset_id.in_(asset_ids),
                Telemetry.metric == "energy_kwh",
                Telemetry.quality != "bad",
                Telemetry.ts >= start_ts,
                Telemetry.ts < end_ts,
            )
        )
        .group_by(Telemetry.asset_id)
    )
    out: Dict[UUID, float] = {}
    for aid, delta in db.execute(stmt).all():
        d = float(delta or 0.0)
        out[aid] = d if d > 0 else 0.0
    return out


def compute_energy_summary(
    db: Session,
    assets: Iterable[Asset],
    start_ts: datetime,
    end_ts: datetime,
) -> EnergySummary:
    """Build an :class:`EnergySummary` for the given assets and window.

    Empty asset list and zero-length windows return a zeroed summary
    instead of raising; the route layer relies on that for the no-data
    case.
    """
    asset_list: List[Asset] = list(assets)
    duration_hours = max((end_ts - start_ts).total_seconds() / 3600.0, 0.0)
    if not asset_list or duration_hours == 0.0:
        return EnergySummary(
            start_ts=start_ts,
            end_ts=end_ts,
            duration_hours=duration_hours,
            asset_count=len(asset_list),
            total_kwh=0.0,
            peak_kw=0.0,
            per_asset=[],
        )

    asset_ids = [a.id for a in asset_list]
    power = _power_stats(db, asset_ids, start_ts, end_ts)
    energy = _energy_consumption(db, asset_ids, start_ts, end_ts)

    per_asset: List[AssetEnergy] = []
    total_kwh = 0.0
    peak_kw = 0.0
    for asset in asset_list:
        avg_kw, mx_kw = power.get(asset.id, (0.0, 0.0))
        # Prefer the cumulative meter reading; fall back to power
        # integration so non-meter assets (compressors, chillers) still
        # contribute a number.
        meter_kwh = energy.get(asset.id)
        if meter_kwh is not None and meter_kwh > 0:
            kwh = meter_kwh
        else:
            kwh = avg_kw * duration_hours

        if mx_kw > peak_kw:
            peak_kw = mx_kw
        total_kwh += kwh

        per_asset.append(
            AssetEnergy(
                asset_id=asset.id,
                asset_name=asset.name,
                asset_type=asset.asset_type,
                energy_kwh=kwh,
                avg_power_kw=avg_kw,
                peak_kw=mx_kw,
            )
        )

    return EnergySummary(
        start_ts=start_ts,
        end_ts=end_ts,
        duration_hours=duration_hours,
        asset_count=len(asset_list),
        total_kwh=total_kwh,
        peak_kw=peak_kw,
        per_asset=per_asset,
    )


# ---------------------------------------------------------------------------
# Alarm roll-up
# ---------------------------------------------------------------------------


_STATE_TO_KEY = {"OPEN": "active", "ACK": "acknowledged", "RESOLVED": "resolved"}


def compute_alarm_summary(
    db: Session,
    assets: Iterable[Asset],
    start_ts: datetime,
    end_ts: datetime,
) -> AlarmSummary:
    """Count alarms opened in the window, broken down by state and severity."""
    asset_ids = [a.id for a in assets]
    by_status: Dict[str, int] = {"active": 0, "acknowledged": 0, "resolved": 0}
    by_severity: Dict[str, int] = {"info": 0, "warning": 0, "critical": 0}
    if not asset_ids:
        return AlarmSummary(by_status=by_status, by_severity=by_severity, total=0)

    rows = db.execute(
        select(Alarm.state, Alarm.severity, func.count())
        .where(
            and_(
                Alarm.asset_id.in_(asset_ids),
                Alarm.opened_at >= start_ts,
                Alarm.opened_at < end_ts,
            )
        )
        .group_by(Alarm.state, Alarm.severity)
    ).all()

    total = 0
    for state, severity, count in rows:
        n = int(count or 0)
        total += n
        key = _STATE_TO_KEY.get(str(state), str(state).lower())
        by_status[key] = by_status.get(key, 0) + n
        sev = str(severity).lower()
        by_severity[sev] = by_severity.get(sev, 0) + n

    return AlarmSummary(by_status=by_status, by_severity=by_severity, total=total)


__all__ = [
    "AssetEnergy",
    "EnergySummary",
    "AlarmSummary",
    "compute_energy_summary",
    "compute_alarm_summary",
]
