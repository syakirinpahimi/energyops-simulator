"""Asset catalogue and value generators for the simulator.

Defines the five demo assets, their sensors, and the per-tick value
generation logic (including anomaly injection). Pure-Python and
deterministic when seeded so the unit tests can pin behaviour.
"""

from __future__ import annotations

import math
import random
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Dict, List, Optional


# ---------------------------------------------------------------------------
# Domain types
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class Sensor:
    """A single measurable signal on an asset."""

    metric: str
    unit: str
    slug: Optional[str] = None  # defaults to metric

    @property
    def topic_slug(self) -> str:
        return self.slug or self.metric


@dataclass(frozen=True)
class Asset:
    """An asset with a stable slug chain and a list of sensors."""

    site_slug: str
    site_name: str
    area_slug: str
    area_name: str
    asset_slug: str
    asset_name: str
    asset_type: str
    sensors: List[Sensor]
    # Optional per-asset tuning the generators use. Kept as a plain dict to
    # avoid one-off dataclasses for every type.
    config: Dict[str, float] = field(default_factory=dict)


@dataclass
class Reading:
    """One published value."""

    asset: Asset
    sensor: Sensor
    value: float
    quality: str = "good"
    anomaly: Optional[str] = None  # short tag describing the anomaly, if any


# ---------------------------------------------------------------------------
# Asset catalogue (the five demo assets from the brief)
# ---------------------------------------------------------------------------


def default_assets() -> List[Asset]:
    """Return the five demo assets described in the brief.

    The slugs follow the topic conventions in ``docs/API_CONTRACT.md``: lower
    case, hyphenated, stable across restarts.
    """

    return [
        Asset(
            site_slug="kuantan-plant",
            site_name="Kuantan Plant",
            area_slug="pump-house",
            area_name="Pump House",
            asset_slug="p-101",
            asset_name="Pump P-101",
            asset_type="pump",
            sensors=[
                Sensor("power_kw", "kW"),
                Sensor("vibration_mm_s", "mm/s"),
                Sensor("flow_m3_h", "m3/h"),
                Sensor("pressure_bar", "bar"),
            ],
            config={"rated_power_kw": 55.0, "rated_flow_m3_h": 120.0},
        ),
        Asset(
            site_slug="kuantan-plant",
            site_name="Kuantan Plant",
            area_slug="utilities",
            area_name="Utilities",
            asset_slug="c-201",
            asset_name="Air Compressor C-201",
            asset_type="compressor",
            sensors=[
                Sensor("power_kw", "kW"),
                Sensor("pressure_bar", "bar"),
                Sensor("temperature_c", "C"),
            ],
            config={"rated_power_kw": 75.0},
        ),
        Asset(
            site_slug="kl-data-centre",
            site_name="KL Data Centre",
            area_slug="chiller-plant",
            area_name="Chiller Plant",
            asset_slug="ch-1",
            asset_name="HVAC Chiller CH-1",
            asset_type="chiller",
            sensors=[
                Sensor("power_kw", "kW"),
                Sensor("temperature_c", "C"),
                Sensor("energy_kwh", "kWh"),
            ],
            config={"rated_power_kw": 180.0},
        ),
        Asset(
            site_slug="johor-solar-farm",
            site_name="Johor Solar Farm",
            area_slug="solar-inverter-field",
            area_name="Solar Inverter Field",
            asset_slug="inv-01",
            asset_name="Solar Inverter INV-01",
            asset_type="inverter",
            sensors=[
                Sensor("power_kw", "kW"),
                Sensor("energy_kwh", "kWh"),
                Sensor("voltage_v", "V"),
                Sensor("current_a", "A"),
            ],
            config={"rated_power_kw": 100.0},
        ),
        Asset(
            site_slug="kuantan-plant",
            site_name="Kuantan Plant",
            area_slug="utilities",
            area_name="Utilities",
            asset_slug="gm-01",
            asset_name="Main Grid Meter GM-01",
            asset_type="meter",
            sensors=[
                Sensor("power_kw", "kW"),
                Sensor("energy_kwh", "kWh"),
                Sensor("voltage_v", "V"),
                Sensor("current_a", "A"),
            ],
            config={"rated_power_kw": 500.0},
        ),
    ]


# ---------------------------------------------------------------------------
# Anomaly catalogue
# ---------------------------------------------------------------------------


# Mapping of asset_slug -> list of anomaly tags this asset can express.
# Tags are short, machine-readable strings the generator uses to bias output.
ANOMALY_CATALOGUE: Dict[str, List[str]] = {
    "pump-p-101":            ["vibration_spike"],
    "air-compressor-c-201":  ["high_temperature"],
    "hvac-chiller-ch-1":     ["high_power_draw"],
    "solar-inverter-inv-01": ["low_output_daytime"],
    "main-grid-meter-gm-01": ["voltage_dip"],
}


# Alarm thresholds the backend can use to evaluate the same readings. They
# are exported here so the simulator and the alarm engine agree on what
# "abnormal" looks like.
ALARM_THRESHOLDS: Dict[str, Dict[str, Dict[str, float]]] = {
    "pump":       {"vibration_mm_s": {"high": 8.0, "severity_critical": 12.0}},
    "compressor": {"temperature_c":  {"high": 95.0, "severity_critical": 110.0}},
    "chiller":    {"power_kw":       {"high": 220.0, "severity_critical": 260.0}},
    "inverter":   {"power_kw":       {"low_daytime": 10.0}},
    "meter":      {"voltage_v":      {"low": 210.0, "severity_critical": 200.0}},
}


# ---------------------------------------------------------------------------
# Per-asset state (runner passes this back in on each tick)
# ---------------------------------------------------------------------------


@dataclass
class AssetState:
    """Mutable per-asset state carried across ticks."""

    # Monotonic counters
    energy_kwh: float = 0.0
    # Active anomaly bookkeeping
    active_anomaly: Optional[str] = None
    anomaly_ticks_left: int = 0
    # Scratch space for generator phase / drift
    drift: float = 0.0


# ---------------------------------------------------------------------------
# Generators
# ---------------------------------------------------------------------------


def _solar_factor(t: datetime) -> float:
    """Return a 0..1 factor for solar production at time ``t``.

    Sunrise ~06:00 local, peak ~13:00 local, sunset ~19:00 local. The
    simulator runs in UTC so we approximate by treating 06–19 as the active
    window. This is a demo curve, not an astronomical model.
    """
    # Use UTC hour-of-day. Good enough for a demo running anywhere in MY-ish
    # timezones (UTC+8 means real local sun would be 6h ahead, but the
    # daylight curve still looks plausible on a chart).
    hour = t.hour + t.minute / 60.0
    if hour < 6.0 or hour > 19.0:
        return 0.0
    # Cosine bump centred on 12.5h, half-width 6.5h.
    return max(0.0, math.cos((hour - 12.5) / 6.5 * (math.pi / 2.0)))


def _gauss(rng: random.Random, mean: float, pct: float) -> float:
    """Return ``mean`` jittered by a gaussian with std-dev ``pct * mean``."""
    sigma = abs(mean) * pct if mean != 0 else pct
    return rng.gauss(mean, sigma)


GeneratorFn = Callable[[Asset, AssetState, datetime, random.Random, Optional[str]], List[Reading]]


def _gen_pump(
    asset: Asset, state: AssetState, t: datetime, rng: random.Random, anomaly: Optional[str]
) -> List[Reading]:
    rated_power = asset.config.get("rated_power_kw", 55.0)
    rated_flow = asset.config.get("rated_flow_m3_h", 120.0)

    # Slow drift gives charts an organic look.
    state.drift += rng.uniform(-0.02, 0.02)
    state.drift = max(-0.15, min(0.15, state.drift))
    duty = 0.75 + state.drift  # 60 - 90% of rated

    power = _gauss(rng, rated_power * duty, 0.02)
    flow = _gauss(rng, rated_flow * duty, 0.03)
    pressure = _gauss(rng, 4.0 + duty * 1.5, 0.02)
    vibration = _gauss(rng, 2.0 + duty * 0.5, 0.10)

    if anomaly == "vibration_spike":
        # Push vibration well over the 8 mm/s warning threshold.
        vibration = _gauss(rng, 14.0, 0.05)
        # Power tends to climb with bearing distress.
        power *= 1.05

    return [
        Reading(asset, asset.sensors[0], round(power, 2), anomaly=anomaly),
        Reading(asset, asset.sensors[1], round(vibration, 3), anomaly=anomaly),
        Reading(asset, asset.sensors[2], round(flow, 2), anomaly=anomaly),
        Reading(asset, asset.sensors[3], round(pressure, 3), anomaly=anomaly),
    ]


def _gen_compressor(
    asset: Asset, state: AssetState, t: datetime, rng: random.Random, anomaly: Optional[str]
) -> List[Reading]:
    rated_power = asset.config.get("rated_power_kw", 75.0)

    # Soft duty cycle modulated by drift.
    state.drift += rng.uniform(-0.03, 0.03)
    state.drift = max(-0.2, min(0.2, state.drift))
    load = 0.7 + state.drift

    power = _gauss(rng, rated_power * load, 0.025)
    pressure = _gauss(rng, 7.5 + load * 0.5, 0.02)
    temperature = _gauss(rng, 65.0 + load * 15.0, 0.03)

    if anomaly == "high_temperature":
        temperature = _gauss(rng, 105.0, 0.02)
        power *= 1.03

    return [
        Reading(asset, asset.sensors[0], round(power, 2), anomaly=anomaly),
        Reading(asset, asset.sensors[1], round(pressure, 3), anomaly=anomaly),
        Reading(asset, asset.sensors[2], round(temperature, 2), anomaly=anomaly),
    ]


def _gen_chiller(
    asset: Asset, state: AssetState, t: datetime, rng: random.Random, anomaly: Optional[str]
) -> List[Reading]:
    rated_power = asset.config.get("rated_power_kw", 180.0)

    state.drift += rng.uniform(-0.02, 0.02)
    state.drift = max(-0.15, min(0.15, state.drift))
    load = 0.8 + state.drift

    power = _gauss(rng, rated_power * load, 0.02)
    temperature = _gauss(rng, 7.0, 0.05)  # chilled-water supply

    if anomaly == "high_power_draw":
        power = _gauss(rng, 250.0, 0.03)
        temperature += 1.5  # cooling falls behind

    # Energy accumulator (kWh += kW * hours_since_last_tick). The runner
    # owns the wall-clock; here we assume one tick is the configured tick
    # interval. We accept a small approximation in exchange for simplicity.
    state.energy_kwh += max(0.0, power) * (5.0 / 3600.0)

    return [
        Reading(asset, asset.sensors[0], round(power, 2), anomaly=anomaly),
        Reading(asset, asset.sensors[1], round(temperature, 2), anomaly=anomaly),
        Reading(asset, asset.sensors[2], round(state.energy_kwh, 3), anomaly=anomaly),
    ]


def _gen_inverter(
    asset: Asset, state: AssetState, t: datetime, rng: random.Random, anomaly: Optional[str]
) -> List[Reading]:
    rated_power = asset.config.get("rated_power_kw", 100.0)
    factor = _solar_factor(t)

    expected_power = rated_power * factor
    power = _gauss(rng, expected_power, 0.04) if factor > 0 else _gauss(rng, 0.0, 0.5)

    voltage = _gauss(rng, 400.0, 0.005) if factor > 0 else 0.0
    current = (power * 1000.0 / voltage) if voltage > 1 else 0.0

    if anomaly == "low_output_daytime" and factor > 0.3:
        power = _gauss(rng, 5.0, 0.5)
        current = (power * 1000.0 / voltage) if voltage > 1 else 0.0

    state.energy_kwh += max(0.0, power) * (5.0 / 3600.0)

    return [
        Reading(asset, asset.sensors[0], round(max(power, 0.0), 2), anomaly=anomaly),
        Reading(asset, asset.sensors[1], round(state.energy_kwh, 3), anomaly=anomaly),
        Reading(asset, asset.sensors[2], round(voltage, 2), anomaly=anomaly),
        Reading(asset, asset.sensors[3], round(current, 2), anomaly=anomaly),
    ]


def _gen_meter(
    asset: Asset, state: AssetState, t: datetime, rng: random.Random, anomaly: Optional[str]
) -> List[Reading]:
    rated_power = asset.config.get("rated_power_kw", 500.0)

    # Diurnal-ish curve.
    hour = t.hour + t.minute / 60.0
    diurnal = 0.6 + 0.3 * math.sin((hour - 6.0) / 24.0 * 2.0 * math.pi)
    state.drift += rng.uniform(-0.02, 0.02)
    state.drift = max(-0.1, min(0.1, state.drift))
    load = max(0.3, diurnal + state.drift)

    power = _gauss(rng, rated_power * load, 0.015)
    voltage = _gauss(rng, 230.0, 0.005)
    current = (power * 1000.0 / voltage) if voltage > 1 else 0.0

    if anomaly == "voltage_dip":
        voltage = _gauss(rng, 198.0, 0.005)
        current = (power * 1000.0 / voltage) if voltage > 1 else 0.0

    state.energy_kwh += max(0.0, power) * (5.0 / 3600.0)

    return [
        Reading(asset, asset.sensors[0], round(power, 2), anomaly=anomaly),
        Reading(asset, asset.sensors[1], round(state.energy_kwh, 3), anomaly=anomaly),
        Reading(asset, asset.sensors[2], round(voltage, 2), anomaly=anomaly),
        Reading(asset, asset.sensors[3], round(current, 2), anomaly=anomaly),
    ]


GENERATORS: Dict[str, GeneratorFn] = {
    "pump":       _gen_pump,
    "compressor": _gen_compressor,
    "chiller":    _gen_chiller,
    "inverter":   _gen_inverter,
    "meter":      _gen_meter,
}


def step(
    asset: Asset,
    state: AssetState,
    now: Optional[datetime],
    rng: random.Random,
    fault_probability: float,
) -> List[Reading]:
    """Advance one tick for ``asset`` and return the readings published."""

    t = now or datetime.now(timezone.utc)

    # Anomaly state machine: hold an active anomaly for a few ticks so the
    # backend's alarm rules see a sustained breach, not a single blip.
    if state.active_anomaly and state.anomaly_ticks_left > 0:
        state.anomaly_ticks_left -= 1
    else:
        state.active_anomaly = None
        if rng.random() < fault_probability:
            choices = ANOMALY_CATALOGUE.get(asset.asset_slug, [])
            if choices:
                state.active_anomaly = rng.choice(choices)
                state.anomaly_ticks_left = rng.randint(3, 6)

    gen = GENERATORS.get(asset.asset_type)
    if gen is None:
        raise ValueError(f"No generator registered for asset_type={asset.asset_type!r}")
    return gen(asset, state, t, rng, state.active_anomaly)


# ---------------------------------------------------------------------------
# Topic helpers
# ---------------------------------------------------------------------------


def topic_for(reading: Reading, *, root: str, company_slug: str = "", channel: str = "telemetry") -> str:
    """Build the MQTT topic for a telemetry reading.

    Layout: ``{root}/{site}/{area}/{asset}/{sensor}`` -- exactly five
    segments so the backend wildcard ``industrial/+/+/+/+`` matches.
    ``company_slug`` and ``channel`` are accepted for API compatibility
    with status/heartbeat callers but are not part of the telemetry
    topic per the brief.
    """
    del company_slug, channel  # not used for telemetry; kept for symmetry
    return "/".join((
        root,
        reading.asset.site_slug,
        reading.asset.area_slug,
        reading.asset.asset_slug,
        reading.sensor.topic_slug,
    ))


def asset_channel_topic(asset: Asset, *, root: str, company_slug: str = "", channel: str) -> str:
    """Topic for a per-asset (non-sensor) channel like status or heartbeat.

    Reuses the sensor slot with a reserved underscore-prefixed name so the
    five-segment wildcard subscription still matches.
    """
    del company_slug  # not used; kept for symmetry with topic_for
    return "/".join((
        root,
        asset.site_slug,
        asset.area_slug,
        asset.asset_slug,
        f"_{channel}",
    ))


def build_payload(reading: Reading, *, company_name: str, ts: datetime) -> Dict[str, object]:
    """Build the JSON payload published on the telemetry channel."""
    return {
        "timestamp": ts.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
        "company": company_name,
        "site": reading.asset.site_name,
        "area": reading.asset.area_name,
        "asset": reading.asset.asset_name,
        "sensor": reading.sensor.metric,
        "metric": reading.sensor.metric,
        "value": reading.value,
        "unit": reading.sensor.unit,
        "quality": reading.quality,
        "anomaly": reading.anomaly,  # nullable; backend treats null as normal
    }

