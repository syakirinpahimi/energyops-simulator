"""Simple threshold-based alarm engine.

Evaluates a single telemetry sample against a static rule table and either
opens a new alarm or returns ``None``. Designed to be called from the MQTT
consumer; deliberately small so it can be unit-tested without a database.

The thresholds intentionally mirror the anomaly catalogue in the simulator
(``simulator/assets.py``) so injected anomalies do trip alarms when the
backend ingests them.
"""
from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Dict, Optional, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.models import Alarm, Asset, Sensor

log = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Rule table
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ThresholdRule:
    """One static threshold rule.

    The comparator is encoded as a string for readability. ``daylight_only``
    rules only evaluate during the simulated solar window (06:00-19:00 UTC)
    so we don't false-trigger an "inverter low output" alarm at midnight.
    """

    code: str
    metric: str
    comparator: str  # 'gt' or 'lt'
    threshold: float
    severity: str    # 'info' | 'warning' | 'critical'
    message_template: str
    daylight_only: bool = False
    critical_threshold: Optional[float] = None  # if breached, severity escalates to 'critical'


# Keyed by ``asset_type`` to keep the table compact. The MQTT consumer
# resolves the asset's type before calling ``evaluate``.
RULES: Dict[str, Tuple[ThresholdRule, ...]] = {
    "pump": (
        ThresholdRule(
            code="VIBRATION_HIGH",
            metric="vibration_mm_s",
            comparator="gt",
            threshold=8.0,
            severity="warning",
            message_template="Vibration {value:.2f} mm/s exceeds {threshold:.1f} mm/s",
            critical_threshold=12.0,
        ),
    ),
    "compressor": (
        ThresholdRule(
            code="TEMP_HIGH",
            metric="temperature_c",
            comparator="gt",
            threshold=95.0,
            severity="warning",
            message_template="Temperature {value:.1f} C exceeds {threshold:.0f} C",
            critical_threshold=110.0,
        ),
    ),
    "chiller": (
        ThresholdRule(
            code="POWER_HIGH",
            metric="power_kw",
            comparator="gt",
            threshold=220.0,
            severity="warning",
            message_template="Power draw {value:.1f} kW exceeds {threshold:.0f} kW",
            critical_threshold=260.0,
        ),
    ),
    "inverter": (
        ThresholdRule(
            code="OUTPUT_LOW",
            metric="power_kw",
            comparator="lt",
            threshold=10.0,
            severity="warning",
            message_template="Inverter output {value:.1f} kW below {threshold:.0f} kW during daylight",
            daylight_only=True,
        ),
    ),
    "meter": (
        ThresholdRule(
            code="VOLTAGE_LOW",
            metric="voltage_v",
            comparator="lt",
            threshold=210.0,
            severity="warning",
            message_template="Voltage {value:.1f} V below {threshold:.0f} V",
            critical_threshold=200.0,
        ),
    ),
}


# ---------------------------------------------------------------------------
# Pure evaluation
# ---------------------------------------------------------------------------


def _is_daylight(ts: datetime) -> bool:
    """Match the simulator's daylight window for inverter rules."""
    hour = ts.astimezone(timezone.utc).hour
    return 6 <= hour <= 19


def _comparator_breached(comparator: str, value: float, threshold: float) -> bool:
    if comparator == "gt":
        return value > threshold
    if comparator == "lt":
        return value < threshold
    if comparator == "gte":
        return value >= threshold
    if comparator == "lte":
        return value <= threshold
    raise ValueError(f"unknown comparator {comparator!r}")


@dataclass
class AlarmDecision:
    """What the engine would like to do for one sample."""

    code: str
    severity: str
    message: str
    threshold: float
    triggered_value: float


def evaluate(
    *,
    asset_type: str,
    metric: str,
    value: float,
    ts: datetime,
) -> Optional[AlarmDecision]:
    """Return an AlarmDecision if any rule for ``asset_type``/``metric`` fires."""
    rules = RULES.get(asset_type, ())
    for rule in rules:
        if rule.metric != metric:
            continue
        if rule.daylight_only and not _is_daylight(ts):
            continue
        if not _comparator_breached(rule.comparator, value, rule.threshold):
            continue
        severity = rule.severity
        if rule.critical_threshold is not None and _comparator_breached(
            rule.comparator, value, rule.critical_threshold
        ):
            severity = "critical"
        message = rule.message_template.format(value=value, threshold=rule.threshold)
        return AlarmDecision(
            code=rule.code,
            severity=severity,
            message=message,
            threshold=rule.threshold,
            triggered_value=value,
        )
    return None


# ---------------------------------------------------------------------------
# Persistence helper
# ---------------------------------------------------------------------------


def open_alarm_if_new(
    session: Session,
    *,
    asset: Asset,
    sensor: Optional[Sensor],
    site_id: UUID,
    decision: AlarmDecision,
    opened_at: datetime,
) -> Optional[Alarm]:
    """Insert an OPEN alarm unless one already exists for ``(asset, code)``.

    Returns the new ``Alarm`` row, or ``None`` if a duplicate was found. A
    partial unique index in the schema ensures only one OPEN alarm per
    ``(asset_id, code)`` exists at a time; we both check up-front (cheap)
    and rely on the index (race-safe).
    """
    existing = session.execute(
        select(Alarm.id)
        .where(Alarm.asset_id == asset.id)
        .where(Alarm.code == decision.code)
        .where(Alarm.state == "OPEN")
        .limit(1)
    ).first()
    if existing is not None:
        return None

    alarm = Alarm(
        site_id=site_id,
        asset_id=asset.id,
        sensor_id=sensor.id if sensor is not None else None,
        code=decision.code,
        severity=decision.severity,
        state="OPEN",
        message=decision.message,
        threshold_value=decision.threshold,
        triggered_value=decision.triggered_value,
        opened_at=opened_at,
    )
    session.add(alarm)
    try:
        session.flush()
    except IntegrityError:
        # Lost the race against another worker. Fine -- the existing OPEN
        # alarm is the source of truth.
        session.rollback()
        log.debug("duplicate alarm prevented by unique index asset=%s code=%s", asset.id, decision.code)
        return None
    return alarm
