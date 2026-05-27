"""Tests for the alarm engine threshold rules.

These are pure-function tests against ``app.services.alarm_engine.evaluate``.
We don't need a database or paho-mqtt to verify the rule table.
"""
from __future__ import annotations

import sys
from datetime import datetime, timezone
from pathlib import Path

# The backend package lives at <repo>/backend; add it to sys.path so we can
# import app.services.alarm_engine without installing it.
ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

import pytest


pytest.importorskip("sqlalchemy", reason="backend deps not installed")

from app.services.alarm_engine import evaluate  # noqa: E402


# Daylight UTC time so daylight_only rules apply.
TS_DAY = datetime(2026, 5, 27, 13, 0, tzinfo=timezone.utc)
TS_NIGHT = datetime(2026, 5, 27, 23, 0, tzinfo=timezone.utc)


def test_pump_vibration_warning():
    decision = evaluate(asset_type="pump", metric="vibration_mm_s", value=9.0, ts=TS_DAY)
    assert decision is not None
    assert decision.code == "VIBRATION_HIGH"
    assert decision.severity == "warning"


def test_pump_vibration_critical_when_well_above_threshold():
    decision = evaluate(asset_type="pump", metric="vibration_mm_s", value=14.0, ts=TS_DAY)
    assert decision is not None
    assert decision.severity == "critical"


def test_pump_vibration_normal_returns_none():
    assert evaluate(asset_type="pump", metric="vibration_mm_s", value=2.0, ts=TS_DAY) is None


def test_compressor_temperature_high():
    decision = evaluate(asset_type="compressor", metric="temperature_c", value=105.0, ts=TS_DAY)
    assert decision is not None
    assert decision.code == "TEMP_HIGH"
    assert decision.severity == "warning"


def test_compressor_temperature_critical():
    decision = evaluate(asset_type="compressor", metric="temperature_c", value=115.0, ts=TS_DAY)
    assert decision is not None
    assert decision.severity == "critical"


def test_chiller_power_high():
    decision = evaluate(asset_type="chiller", metric="power_kw", value=240.0, ts=TS_DAY)
    assert decision is not None
    assert decision.code == "POWER_HIGH"


def test_inverter_low_output_only_during_daylight():
    # Daylight: rule fires.
    day = evaluate(asset_type="inverter", metric="power_kw", value=2.0, ts=TS_DAY)
    assert day is not None
    assert day.code == "OUTPUT_LOW"

    # Night: rule must NOT fire (we expect zero output at night).
    night = evaluate(asset_type="inverter", metric="power_kw", value=2.0, ts=TS_NIGHT)
    assert night is None


def test_meter_voltage_low_warning_and_critical():
    warning = evaluate(asset_type="meter", metric="voltage_v", value=205.0, ts=TS_DAY)
    assert warning is not None
    assert warning.severity == "warning"

    critical = evaluate(asset_type="meter", metric="voltage_v", value=195.0, ts=TS_DAY)
    assert critical is not None
    assert critical.severity == "critical"


def test_unknown_asset_type_returns_none():
    assert evaluate(asset_type="unknown", metric="power_kw", value=1.0, ts=TS_DAY) is None


def test_unrelated_metric_returns_none():
    assert evaluate(asset_type="pump", metric="power_kw", value=99999, ts=TS_DAY) is None
