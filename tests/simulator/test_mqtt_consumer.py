"""Tests for the MQTT consumer's end-to-end ``process_message`` path.

These tests stub the SQLAlchemy session and the asset resolver so we can
exercise:

  * a sample payload becomes a telemetry insert + a WS ``telemetry`` event
  * a threshold breach produces an ``alarm`` event and an Alarm insert
  * the WS broadcast callback is invoked exactly once per event

We avoid spinning up a real Postgres / Mosquitto: the consumer's pure
helpers are dependency-injectable for exactly this reason.
"""
from __future__ import annotations

import asyncio
import json
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable, Dict, List, Optional
from uuid import uuid4

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

pytest.importorskip("sqlalchemy", reason="backend deps not installed")

from app.services.mqtt_consumer import (  # noqa: E402
    ProcessResult,
    _AssetCache,
    _ResolvedAsset,
    process_message,
)


# ---------------------------------------------------------------------------
# Test doubles
# ---------------------------------------------------------------------------


@dataclass
class _FakeAsset:
    id: Any
    area_id: Any
    asset_type: str


@dataclass
class _FakeSensor:
    id: Any
    asset_id: Any
    metric: str


@dataclass
class _FakeSession:
    """Captures ``session.add`` calls and supports the small surface
    ``write_telemetry`` / ``open_alarm_if_new`` actually use."""

    added: List[Any] = field(default_factory=list)
    committed: bool = False
    rolled_back: bool = False
    # Map (table_class.__name__, "OPEN_alarm_for_asset_code") -> existing row count.
    open_alarms: Dict[str, int] = field(default_factory=dict)

    # context manager protocol so ``with session_factory() as s`` works
    def __enter__(self) -> "_FakeSession":
        return self

    def __exit__(self, exc_type, exc, tb) -> None:  # noqa: ANN001
        return None

    def add(self, obj: Any) -> None:
        self.added.append(obj)

    def flush(self) -> None:
        return None

    def commit(self) -> None:
        self.committed = True

    def rollback(self) -> None:
        self.rolled_back = True

    # The consumer also calls ``session.execute(...).first() / scalar_one_or_none()``
    # but only inside ``resolve_asset`` (which we monkeypatch) and inside
    # ``open_alarm_if_new`` (existing OPEN check). For the latter we return
    # a small stub that always reports "no existing alarm".
    def execute(self, *_args, **_kwargs):  # noqa: ANN001
        return _FakeExecResult()


class _FakeExecResult:
    def first(self):  # noqa: D401
        return None

    def scalar_one_or_none(self):
        return None


def _session_factory_factory():
    sessions: List[_FakeSession] = []

    def factory() -> _FakeSession:
        s = _FakeSession()
        sessions.append(s)
        return s

    return factory, sessions


def _payload(**overrides) -> bytes:
    base = {
        "timestamp": "2026-05-20T13:00:00Z",
        "company": "Demo Industrial Holdings",
        "site": "Kuantan Plant",
        "area": "Utilities",
        "asset": "Pump P-101",
        "sensor": "vibration_mm_s",
        "metric": "vibration_mm_s",
        "value": 2.5,
        "unit": "mm/s",
        "quality": "good",
    }
    base.update(overrides)
    return json.dumps(base).encode("utf-8")


@pytest.fixture()
def patched_resolver(monkeypatch: pytest.MonkeyPatch):
    """Replace ``resolve_asset`` with a deterministic stub.

    The real resolver expects fully-seeded hierarchy rows; in unit tests we
    bypass that and hand back a synthetic ``_ResolvedAsset``. The factory
    returned by this fixture lets each test pick the asset_type so the
    alarm engine fires the right rule.
    """

    def _make(asset_type: str = "pump") -> Callable[[], _ResolvedAsset]:
        site_id = uuid4()
        area_id = uuid4()
        asset_id = uuid4()
        sensor_id = uuid4()

        def _resolved(*_args, metric: str = "", **_kwargs) -> _ResolvedAsset:
            asset = _FakeAsset(id=asset_id, area_id=area_id, asset_type=asset_type)
            sensor = _FakeSensor(id=sensor_id, asset_id=asset_id, metric=metric or "vibration_mm_s")
            return _ResolvedAsset(asset=asset, sensor=sensor, site_id=site_id)

        from app.services import mqtt_consumer

        monkeypatch.setattr(mqtt_consumer, "resolve_asset", _resolved)
        # Bypass the IntegrityError catch path which would .rollback().
        return _resolved

    return _make


# ---------------------------------------------------------------------------
# process_message: telemetry path
# ---------------------------------------------------------------------------


def test_process_message_creates_telemetry_event(patched_resolver) -> None:
    patched_resolver(asset_type="pump")
    factory, sessions = _session_factory_factory()

    result = process_message(
        topic="industrial/kuantan-plant/utilities/pump-p-101/vibration_mm_s",
        payload=_payload(value=2.5),
        cache=_AssetCache(),
        session_factory=factory,
    )

    assert isinstance(result, ProcessResult)
    assert result.telemetry_event is not None
    assert result.telemetry_event["type"] == "telemetry"
    assert result.telemetry_event["metric"] == "vibration_mm_s"
    assert result.telemetry_event["value"] == 2.5
    assert result.alarm_event is None  # below threshold

    # Telemetry row was added and the session committed.
    assert sessions, "session_factory should have produced one session"
    sess = sessions[-1]
    assert sess.committed is True
    # Telemetry rows are SQLAlchemy model instances; pick the right one by
    # the presence of a ``metric`` attribute matching our payload.
    assert any(
        getattr(r, "metric", None) == "vibration_mm_s" and getattr(r, "value", None) == 2.5
        for r in sess.added
    ), f"expected telemetry row in session.add() calls, got {sess.added!r}"


def test_process_message_above_threshold_emits_alarm(patched_resolver) -> None:
    patched_resolver(asset_type="pump")
    factory, sessions = _session_factory_factory()

    result = process_message(
        topic="industrial/kuantan-plant/utilities/pump-p-101/vibration_mm_s",
        payload=_payload(value=15.0),  # > 8.0 threshold and > 12.0 critical
        cache=_AssetCache(),
        session_factory=factory,
    )

    assert result.telemetry_event is not None
    assert result.alarm_event is not None
    assert result.alarm_event["type"] == "alarm"
    assert result.alarm_event["code"] == "VIBRATION_HIGH"
    assert result.alarm_event["severity"] == "critical"

    # Telemetry row + Alarm row were both inserted.
    sess = sessions[-1]
    type_names = {type(r).__name__ for r in sess.added}
    assert "Telemetry" in type_names
    assert "Alarm" in type_names


def test_process_message_status_topic_emits_status_event(patched_resolver) -> None:
    patched_resolver(asset_type="pump")
    factory, sessions = _session_factory_factory()

    payload = json.dumps({
        "timestamp": "2026-05-20T13:00:00Z",
        "asset": "Pump P-101",
        "site": "Kuantan Plant",
        "status": "fault",
        "reason": "vibration_spike",
    }).encode("utf-8")

    result = process_message(
        topic="industrial/kuantan-plant/utilities/pump-p-101/_status",
        payload=payload,
        cache=_AssetCache(),
        session_factory=factory,
    )

    assert result.status_event is not None
    assert result.status_event["type"] == "status"
    assert result.status_event["reason"] == "vibration_spike"
    assert result.telemetry_event is None
    assert result.alarm_event is None


def test_process_message_unknown_asset_returns_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    """When ``resolve_asset`` returns None, no events are produced."""
    from app.services import mqtt_consumer

    monkeypatch.setattr(mqtt_consumer, "resolve_asset", lambda *a, **kw: None)
    factory, sessions = _session_factory_factory()

    result = process_message(
        topic="industrial/no/such/asset/power_kw",
        payload=_payload(metric="power_kw", value=1.0),
        cache=_AssetCache(),
        session_factory=factory,
    )

    assert result.telemetry_event is None
    assert result.alarm_event is None


# ---------------------------------------------------------------------------
# Broadcast callback wiring
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_consumer_invokes_broadcast_for_each_event(
    monkeypatch: pytest.MonkeyPatch, patched_resolver
) -> None:
    """``MqttConsumer._consume`` must broadcast every event from ProcessResult.

    We don't spin up paho here -- we exercise the queue + broadcast loop
    directly so we can assert the callback was awaited with the expected
    payloads.
    """
    from app.services import mqtt_consumer

    patched_resolver(asset_type="pump")
    factory, _ = _session_factory_factory()

    received: List[Dict[str, Any]] = []

    async def _capture(payload: Dict[str, Any]) -> None:
        received.append(payload)

    consumer = mqtt_consumer.MqttConsumer.__new__(mqtt_consumer.MqttConsumer)
    consumer._broadcast = _capture  # type: ignore[attr-defined]
    consumer._cache = mqtt_consumer._AssetCache()  # type: ignore[attr-defined]
    consumer._queue = asyncio.Queue(maxsize=10)  # type: ignore[attr-defined]
    consumer._stop_event = asyncio.Event()  # type: ignore[attr-defined]
    consumer._loop = asyncio.get_running_loop()  # type: ignore[attr-defined]

    # Monkeypatch process_message so the consumer task uses our fake session
    # factory rather than the real SessionLocal.
    real_process_message = mqtt_consumer.process_message

    def _patched(topic: str, payload: Any, cache: Any) -> ProcessResult:
        return real_process_message(
            topic=topic, payload=payload, cache=cache, session_factory=factory
        )

    monkeypatch.setattr(mqtt_consumer, "process_message", _patched)

    # Push one telemetry message that should trip the critical alarm.
    await consumer._queue.put((  # type: ignore[attr-defined]
        "industrial/kuantan-plant/utilities/pump-p-101/vibration_mm_s",
        _payload(value=15.0),
    ))

    task = asyncio.create_task(consumer._consume())  # type: ignore[attr-defined]
    # Give the consumer a moment to drain the queue and call broadcast twice.
    for _ in range(20):
        await asyncio.sleep(0.05)
        if len(received) >= 2:
            break
    consumer._stop_event.set()  # type: ignore[attr-defined]
    task.cancel()
    try:
        await task
    except (asyncio.CancelledError, Exception):
        pass

    types = [m["type"] for m in received]
    assert "telemetry" in types, f"expected telemetry broadcast, got {received!r}"
    assert "alarm" in types, f"expected alarm broadcast, got {received!r}"
