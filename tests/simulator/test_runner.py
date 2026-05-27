"""Tests for the SimulatorRunner using the in-memory publisher."""
from __future__ import annotations

import json
from datetime import datetime, timezone

from simulator.config import Settings
from simulator.main import InMemoryPublisher, SimulatorRunner


def _settings(seed: int = 1) -> Settings:
    return Settings(random_seed=seed, fault_probability=0.0, tick_seconds=0.01)


def test_runner_publishes_one_message_per_sensor():
    pub = InMemoryPublisher()
    runner = SimulatorRunner(_settings(), pub)
    runner.tick(now=datetime(2026, 5, 27, 13, 0, tzinfo=timezone.utc))

    # Total telemetry messages should equal sum of sensors per asset.
    expected_telemetry = sum(len(a.sensors) for a in runner.assets)
    telemetry = [m for m in pub.messages if not m["topic"].endswith(("_status", "_heartbeat"))]
    assert len(telemetry) == expected_telemetry


def test_runner_emits_status_when_anomaly_active():
    # Force an anomaly by setting fault_probability to 1.0
    pub = InMemoryPublisher()
    settings = Settings(random_seed=42, fault_probability=1.0, tick_seconds=0.01)
    runner = SimulatorRunner(settings, pub)
    runner.tick(now=datetime(2026, 5, 27, 13, 0, tzinfo=timezone.utc))

    status_msgs = [m for m in pub.messages if m["topic"].endswith("/_status")]
    assert status_msgs, "expected at least one status message when fault_probability=1.0"
    payload = json.loads(status_msgs[0]["payload"])
    assert payload["status"] == "fault"
    assert status_msgs[0]["retain"] is True


def test_runner_publishes_heartbeat_on_first_tick():
    pub = InMemoryPublisher()
    runner = SimulatorRunner(_settings(), pub)
    runner.tick(now=datetime(2026, 5, 27, 13, 0, tzinfo=timezone.utc))

    heartbeats = [m for m in pub.messages if m["topic"].endswith("/_heartbeat")]
    # One heartbeat per asset on the first tick.
    assert len(heartbeats) == len(runner.assets)


def test_runner_is_deterministic_with_seed():
    ts = datetime(2026, 5, 27, 13, 0, tzinfo=timezone.utc)

    pub_a = InMemoryPublisher()
    SimulatorRunner(_settings(seed=99), pub_a).tick(now=ts)

    pub_b = InMemoryPublisher()
    SimulatorRunner(_settings(seed=99), pub_b).tick(now=ts)

    assert [m["topic"] for m in pub_a.messages] == [m["topic"] for m in pub_b.messages]
    assert [m["payload"] for m in pub_a.messages] == [m["payload"] for m in pub_b.messages]
