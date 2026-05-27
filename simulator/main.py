"""Simulator entrypoint.

Publishes synthetic telemetry to MQTT for the five demo assets every
``SIM_TICK_SECONDS`` seconds and occasionally injects anomalies. Designed
to be runnable in three modes:

* ``python -m simulator.main`` -- run forever
* ``python -m simulator.main --smoke`` -- run a short deterministic burst
  and exit; useful in CI and as a manual sanity check
* ``python -m simulator.main --once`` -- publish exactly one tick per
  asset and exit
"""

from __future__ import annotations

import argparse
import json
import logging
import random
import signal
import sys
import time
from datetime import datetime, timezone
from typing import Dict, List, Optional

try:  # paho is optional at import time so unit tests can run without it.
    import paho.mqtt.client as mqtt
except ImportError:  # pragma: no cover - exercised only when paho missing
    mqtt = None  # type: ignore[assignment]

from simulator import assets as assets_mod
from simulator.assets import (
    Asset,
    AssetState,
    Reading,
    asset_channel_topic,
    build_payload,
    default_assets,
    step,
    topic_for,
)
from simulator.config import Settings, configure_logging, load_settings


log = logging.getLogger("simulator")


# ---------------------------------------------------------------------------
# MQTT publisher abstraction
# ---------------------------------------------------------------------------


class Publisher:
    """Tiny wrapper around ``paho.mqtt`` that can be swapped in tests."""

    def publish(self, topic: str, payload: str, *, qos: int = 1, retain: bool = False) -> None:
        raise NotImplementedError

    def start(self) -> None:  # pragma: no cover - default no-op
        pass

    def stop(self) -> None:  # pragma: no cover - default no-op
        pass


class MqttPublisher(Publisher):
    """Real MQTT publisher backed by paho-mqtt."""

    def __init__(self, settings: Settings) -> None:
        if mqtt is None:
            raise RuntimeError(
                "paho-mqtt is not installed. Install simulator/requirements.txt "
                "or run with InMemoryPublisher (smoke mode without --mqtt)."
            )
        self._client = mqtt.Client(client_id=settings.mqtt_client_id, clean_session=True)
        if settings.mqtt_username:
            self._client.username_pw_set(settings.mqtt_username, settings.mqtt_password or "")
        self._client.on_connect = self._on_connect
        self._client.on_disconnect = self._on_disconnect
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)
        self._settings = settings

    def _on_connect(self, client, userdata, flags, rc) -> None:  # noqa: ANN001 - paho signature
        if rc == 0:
            log.info("mqtt connected host=%s port=%d", self._settings.mqtt_host, self._settings.mqtt_port)
        else:
            log.warning("mqtt connect failed rc=%s", rc)

    def _on_disconnect(self, client, userdata, rc) -> None:  # noqa: ANN001 - paho signature
        if rc != 0:
            log.warning("mqtt disconnected rc=%s; will reconnect", rc)

    def start(self) -> None:
        self._client.connect_async(self._settings.mqtt_host, self._settings.mqtt_port, self._settings.mqtt_keepalive)
        self._client.loop_start()

    def stop(self) -> None:
        try:
            self._client.loop_stop()
            self._client.disconnect()
        except Exception:  # pragma: no cover - best-effort shutdown
            log.exception("error while stopping mqtt client")

    def publish(self, topic: str, payload: str, *, qos: int = 1, retain: bool = False) -> None:
        info = self._client.publish(topic, payload=payload, qos=qos, retain=retain)
        if info.rc != 0:
            log.warning("publish failed topic=%s rc=%s", topic, info.rc)


class InMemoryPublisher(Publisher):
    """Captures published messages in memory. Used for smoke tests."""

    def __init__(self) -> None:
        self.messages: List[Dict[str, object]] = []

    def publish(self, topic: str, payload: str, *, qos: int = 1, retain: bool = False) -> None:
        self.messages.append({"topic": topic, "payload": payload, "qos": qos, "retain": retain})


# ---------------------------------------------------------------------------
# Tick loop
# ---------------------------------------------------------------------------


class SimulatorRunner:
    """Owns the per-asset state and drives one tick at a time."""

    def __init__(
        self,
        settings: Settings,
        publisher: Publisher,
        asset_list: Optional[List[Asset]] = None,
        rng: Optional[random.Random] = None,
    ) -> None:
        self.settings = settings
        self.publisher = publisher
        self.assets: List[Asset] = asset_list if asset_list is not None else default_assets()
        self._states: Dict[str, AssetState] = {a.asset_slug: AssetState() for a in self.assets}
        self.rng = rng or random.Random(settings.random_seed)
        self._last_status: Dict[str, str] = {}
        self._last_heartbeat: Dict[str, float] = {}

    # -- Public API -------------------------------------------------------

    def tick(self, now: Optional[datetime] = None) -> List[Reading]:
        """Run one tick across all assets. Returns the published readings."""
        ts = now or datetime.now(timezone.utc)
        all_readings: List[Reading] = []
        for asset in self.assets:
            state = self._states[asset.asset_slug]
            readings = step(asset, state, ts, self.rng, self.settings.fault_probability)
            self._publish_readings(readings, ts)
            self._maybe_publish_status(asset, state, ts)
            self._maybe_publish_heartbeat(asset, ts)
            all_readings.extend(readings)
        return all_readings

    # -- Helpers ----------------------------------------------------------

    def _publish_readings(self, readings: List[Reading], ts: datetime) -> None:
        for r in readings:
            topic = topic_for(r, root=self.settings.topic_root)
            payload = build_payload(r, company_name=self.settings.display_company, ts=ts)
            self.publisher.publish(topic, json.dumps(payload), qos=1, retain=False)
            log.info(
                "publish %s value=%s unit=%s%s",
                topic,
                payload["value"],
                payload["unit"],
                f" anomaly={r.anomaly}" if r.anomaly else "",
            )

    def _maybe_publish_status(self, asset: Asset, state: AssetState, ts: datetime) -> None:
        desired = "fault" if state.active_anomaly else "online"
        if self._last_status.get(asset.asset_slug) == desired:
            return
        self._last_status[asset.asset_slug] = desired
        topic = asset_channel_topic(asset, root=self.settings.topic_root, channel="status")
        payload = {
            "timestamp": ts.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "asset": asset.asset_name,
            "site": asset.site_name,
            "status": desired,
            "reason": state.active_anomaly or "heartbeat_ok",
        }
        self.publisher.publish(topic, json.dumps(payload), qos=1, retain=True)
        log.info("status %s -> %s", asset.asset_slug, desired)

    def _maybe_publish_heartbeat(self, asset: Asset, ts: datetime) -> None:
        # One heartbeat every ~30s per asset.
        last = self._last_heartbeat.get(asset.asset_slug, 0.0)
        if ts.timestamp() - last < 30.0:
            return
        self._last_heartbeat[asset.asset_slug] = ts.timestamp()
        topic = asset_channel_topic(asset, root=self.settings.topic_root, channel="heartbeat")
        payload = {
            "timestamp": ts.astimezone(timezone.utc).isoformat().replace("+00:00", "Z"),
            "asset": asset.asset_name,
        }
        self.publisher.publish(topic, json.dumps(payload), qos=1, retain=False)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------


def _build_arg_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description="EnergyOps telemetry simulator")
    p.add_argument("--smoke", action="store_true", help="Run a short deterministic burst and exit (uses in-memory publisher unless --mqtt is set).")
    p.add_argument("--mqtt", action="store_true", help="Force the MQTT publisher even in smoke mode.")
    p.add_argument("--once", action="store_true", help="Publish one tick across all assets and exit.")
    p.add_argument("--ticks", type=int, default=None, help="Stop after this many ticks (overrides SIM_MAX_TICKS).")
    p.add_argument("--seed", type=int, default=None, help="Random seed for deterministic runs (overrides SIM_RANDOM_SEED).")
    return p


def _make_publisher(settings: Settings, *, smoke: bool, force_mqtt: bool) -> Publisher:
    if smoke and not force_mqtt:
        log.info("using in-memory publisher (smoke mode)")
        return InMemoryPublisher()
    return MqttPublisher(settings)


def run(settings: Settings, *, runner: SimulatorRunner, max_ticks: Optional[int], max_seconds: Optional[float]) -> None:
    """Drive the runner until a termination condition is met."""
    stop = {"flag": False}

    def _handler(signum, frame):  # noqa: ANN001 - signal signature
        log.info("signal %s received, shutting down", signum)
        stop["flag"] = True

    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            signal.signal(sig, _handler)
        except (ValueError, AttributeError):  # pragma: no cover - non-main thread / windows
            pass

    started = time.monotonic()
    tick_index = 0
    while not stop["flag"]:
        runner.tick()
        tick_index += 1
        if max_ticks is not None and tick_index >= max_ticks:
            log.info("reached max_ticks=%d, exiting", max_ticks)
            break
        if max_seconds is not None and (time.monotonic() - started) >= max_seconds:
            log.info("reached max_seconds=%s, exiting", max_seconds)
            break
        # Sleep with jitter; honour Ctrl-C quickly by sleeping in small slices.
        target = settings.tick_seconds
        if settings.tick_jitter > 0:
            target += runner.rng.uniform(-settings.tick_jitter, settings.tick_jitter)
        target = max(0.1, target)
        slept = 0.0
        while slept < target and not stop["flag"]:
            chunk = min(0.25, target - slept)
            time.sleep(chunk)
            slept += chunk


def main(argv: Optional[List[str]] = None) -> int:
    args = _build_arg_parser().parse_args(argv)
    settings = load_settings()
    if args.seed is not None:
        # Frozen dataclass: replace by rebuilding with the override.
        from dataclasses import replace
        settings = replace(settings, random_seed=args.seed)

    configure_logging(settings)
    log.info(
        "simulator starting tick=%.1fs fault_p=%.4f seed=%s assets=%d",
        settings.tick_seconds,
        settings.fault_probability,
        settings.random_seed,
        len(default_assets()),
    )

    publisher = _make_publisher(settings, smoke=args.smoke, force_mqtt=args.mqtt)
    publisher.start()
    try:
        runner = SimulatorRunner(settings, publisher)

        if args.once:
            runner.tick()
            return 0

        if args.smoke:
            # Smoke: run a fixed number of ticks fast so CI sees output quickly.
            from dataclasses import replace
            smoke_settings = replace(settings, tick_seconds=0.2, random_seed=settings.random_seed or 42)
            smoke_runner = SimulatorRunner(smoke_settings, publisher)
            run(smoke_settings, runner=smoke_runner, max_ticks=args.ticks or 10, max_seconds=10.0)
            if isinstance(publisher, InMemoryPublisher):
                log.info("smoke captured %d messages", len(publisher.messages))
            return 0

        run(
            settings,
            runner=runner,
            max_ticks=args.ticks if args.ticks is not None else settings.max_ticks,
            max_seconds=settings.max_seconds,
        )
        return 0
    finally:
        publisher.stop()


if __name__ == "__main__":  # pragma: no cover - manual entrypoint
    sys.exit(main())
