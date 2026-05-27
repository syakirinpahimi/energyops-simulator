"""Tests for the FastAPI app lifespan wiring of the MQTT consumer.

We don't talk to a real broker; instead we monkeypatch
``app.main.MqttConsumer`` import path to a recording stub and check that
``start`` is awaited on lifespan startup and ``stop`` on shutdown.
"""
from __future__ import annotations

import asyncio
import sys
from pathlib import Path
from typing import Any, Optional

import pytest

ROOT = Path(__file__).resolve().parents[1]
BACKEND = ROOT
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

pytest.importorskip("fastapi", reason="backend deps not installed")

from fastapi.testclient import TestClient  # noqa: E402


class _RecordingConsumer:
    """Stand-in for ``MqttConsumer`` that records lifecycle calls."""

    instances: list = []

    def __init__(self, *, broadcast=None, **_kwargs: Any) -> None:
        self.broadcast = broadcast
        self.started = False
        self.stopped = False
        _RecordingConsumer.instances.append(self)

    async def start(self) -> None:
        self.started = True

    async def stop(self) -> None:
        self.stopped = True


@pytest.fixture(autouse=True)
def _reset_consumer_log() -> None:
    _RecordingConsumer.instances.clear()
    yield
    _RecordingConsumer.instances.clear()


def test_lifespan_starts_and_stops_mqtt_consumer(monkeypatch: pytest.MonkeyPatch) -> None:
    """The lifespan must call ``start`` on entry and ``stop`` on exit.

    We replace the real ``MqttConsumer`` import inside ``app.main.lifespan``
    by patching the module attribute on ``app.services.mqtt_consumer``.
    """
    import app.services.mqtt_consumer as mqtt_module

    monkeypatch.setattr(mqtt_module, "MqttConsumer", _RecordingConsumer)
    monkeypatch.setenv("MQTT_ENABLED", "1")

    from app.main import app

    with TestClient(app) as client:
        # Trigger one request so the lifespan startup has definitely run.
        resp = client.get("/health")
        assert resp.status_code == 200
        # The consumer should be exposed on app.state for tests to inspect.
        assert isinstance(app.state.mqtt_consumer, _RecordingConsumer)
        assert app.state.mqtt_consumer.started is True
        # Broadcast must be wired to the ws_hub.
        from app.services.ws_hub import hub
        assert app.state.mqtt_consumer.broadcast == hub.broadcast
        assert getattr(app.state.mqtt_consumer.broadcast, "__self__", None) is hub

    # After the context manager exits, ``stop`` should have been awaited.
    assert _RecordingConsumer.instances, "consumer should have been instantiated"
    assert _RecordingConsumer.instances[-1].stopped is True


def test_lifespan_skips_consumer_when_disabled(monkeypatch: pytest.MonkeyPatch) -> None:
    """``MQTT_ENABLED=0`` keeps the consumer off without breaking the app."""
    import app.services.mqtt_consumer as mqtt_module

    monkeypatch.setattr(mqtt_module, "MqttConsumer", _RecordingConsumer)
    monkeypatch.setenv("MQTT_ENABLED", "0")

    from app.main import app

    with TestClient(app) as client:
        assert client.get("/health").status_code == 200
        assert app.state.mqtt_consumer is None

    assert _RecordingConsumer.instances == []


def test_lifespan_survives_consumer_start_failure(monkeypatch: pytest.MonkeyPatch) -> None:
    """If the consumer raises during start, the API must still come up."""

    class _Boom(_RecordingConsumer):
        async def start(self) -> None:  # type: ignore[override]
            raise RuntimeError("broker missing")

    import app.services.mqtt_consumer as mqtt_module

    monkeypatch.setattr(mqtt_module, "MqttConsumer", _Boom)
    monkeypatch.setenv("MQTT_ENABLED", "1")

    from app.main import app

    with TestClient(app) as client:
        # /health must still respond, proving the API didn't crash.
        assert client.get("/health").status_code == 200
        assert app.state.mqtt_consumer is None
