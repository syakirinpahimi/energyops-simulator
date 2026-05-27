"""Tests for the asset catalogue and per-tick generators.

These are pure-function tests: no MQTT, no clocks. We pin the random seed
so failures are reproducible.
"""
from __future__ import annotations

import random
from datetime import datetime, timezone

import pytest

from simulator.assets import (
    ANOMALY_CATALOGUE,
    AssetState,
    default_assets,
    step,
)


@pytest.fixture
def fixed_time() -> datetime:
    # 13:00 UTC -- inside the simulated solar window so inverter generates power.
    return datetime(2026, 5, 27, 13, 0, 0, tzinfo=timezone.utc)


def _find(asset_slug: str):
    for a in default_assets():
        if a.asset_slug == asset_slug:
            return a
    raise AssertionError(f"asset {asset_slug} missing from default_assets()")


def test_default_assets_has_expected_five():
    slugs = [a.asset_slug for a in default_assets()]
    assert slugs == [
        "p-101",
        "c-201",
        "ch-1",
        "inv-01",
        "gm-01",
    ]


def test_each_asset_has_expected_sensors():
    sensors_by_asset = {a.asset_slug: [s.metric for s in a.sensors] for a in default_assets()}
    assert sensors_by_asset["p-101"] == ["power_kw", "vibration_mm_s", "flow_m3_h", "pressure_bar"]
    assert sensors_by_asset["c-201"] == ["power_kw", "pressure_bar", "temperature_c"]
    assert sensors_by_asset["ch-1"] == ["power_kw", "temperature_c", "energy_kwh"]
    assert sensors_by_asset["inv-01"] == ["power_kw", "energy_kwh", "voltage_v", "current_a"]
    assert sensors_by_asset["gm-01"] == ["power_kw", "energy_kwh", "voltage_v", "current_a"]


def test_step_returns_one_reading_per_sensor(fixed_time):
    rng = random.Random(42)
    for asset in default_assets():
        state = AssetState()
        readings = step(asset, state, fixed_time, rng, fault_probability=0.0)
        assert len(readings) == len(asset.sensors)
        for r, sensor in zip(readings, asset.sensors):
            assert r.sensor.metric == sensor.metric
            assert r.asset is asset


def test_pump_normal_values_within_reasonable_range(fixed_time):
    asset = _find("p-101")
    rng = random.Random(123)
    state = AssetState()
    # Run a handful of ticks so drift settles.
    for _ in range(20):
        readings = step(asset, state, fixed_time, rng, fault_probability=0.0)
    by_metric = {r.sensor.metric: r.value for r in readings}
    assert 20 < by_metric["power_kw"] < 80
    assert 0 < by_metric["vibration_mm_s"] < 6
    assert 50 < by_metric["flow_m3_h"] < 150
    assert 3 < by_metric["pressure_bar"] < 7


def test_step_is_deterministic_with_seed(fixed_time):
    asset = _find("ch-1")
    rng_a = random.Random(7)
    rng_b = random.Random(7)
    state_a = AssetState()
    state_b = AssetState()
    out_a = [step(asset, state_a, fixed_time, rng_a, 0.0) for _ in range(5)]
    out_b = [step(asset, state_b, fixed_time, rng_b, 0.0) for _ in range(5)]
    values_a = [[r.value for r in tick] for tick in out_a]
    values_b = [[r.value for r in tick] for tick in out_b]
    assert values_a == values_b


def test_anomaly_catalogue_covers_all_demo_assets():
    expected = {a.asset_slug for a in default_assets()}
    assert set(ANOMALY_CATALOGUE) == expected


def test_chiller_energy_is_monotonic(fixed_time):
    asset = _find("ch-1")
    rng = random.Random(0)
    state = AssetState()
    last = -1.0
    for _ in range(30):
        readings = step(asset, state, fixed_time, rng, 0.0)
        energy = next(r.value for r in readings if r.sensor.metric == "energy_kwh")
        assert energy >= last
        last = energy
