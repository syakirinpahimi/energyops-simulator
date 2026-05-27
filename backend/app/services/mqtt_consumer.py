"""MQTT consumer that ingests simulator telemetry.

Subscribes to ``industrial/+/+/+/+`` (the topic shape published by the
simulator), parses each payload, writes the reading to the ``telemetry``
hypertable, and asks the alarm engine whether to open an alarm.

Designed to be called from the FastAPI lifespan as a background task. Pure
parsing and rule-evaluation paths are split out so they can be unit-tested
without a real broker.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Dict, Iterable, Optional, Tuple
from uuid import UUID

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError, SQLAlchemyError
from sqlalchemy.orm import Session

from app.config import settings
from app.db import SessionLocal
from app.models import Area, Asset, Sensor, Site, Telemetry
from app.services.alarm_engine import AlarmDecision, evaluate, open_alarm_if_new

try:  # paho is the preferred client; we soft-import so unit tests can run.
    import paho.mqtt.client as mqtt
except ImportError:  # pragma: no cover - exercised only when paho missing
    mqtt = None  # type: ignore[assignment]

log = logging.getLogger(__name__)


TOPIC_FILTER = "industrial/+/+/+/+"
EXPECTED_SEGMENTS = 5  # industrial / site / area / asset / sensor


# ---------------------------------------------------------------------------
# Pure helpers (no DB, no broker)
# ---------------------------------------------------------------------------


@dataclass(frozen=True)
class ParsedReading:
    """Result of parsing one MQTT message into structured form."""

    site_slug: str
    area_slug: str
    asset_slug: str
    sensor_slug: str
    metric: str
    value: float
    unit: str
    quality: str
    ts: datetime
    anomaly: Optional[str]
    is_status: bool
    is_heartbeat: bool


def parse_topic(topic: str) -> Optional[Tuple[str, str, str, str, str]]:
    """Split a topic into ``(root, site, area, asset, sensor_or_channel)``.

    Returns ``None`` if the shape doesn't match the contract.
    """
    parts = topic.split("/")
    if len(parts) != EXPECTED_SEGMENTS:
        return None
    return tuple(parts)  # type: ignore[return-value]


def parse_message(topic: str, payload: bytes | str) -> Optional[ParsedReading]:
    """Parse one MQTT message; return ``None`` if it should be skipped."""
    parts = parse_topic(topic)
    if parts is None:
        log.warning("ignoring topic with wrong shape: %s", topic)
        return None
    _root, site_slug, area_slug, asset_slug, sensor_slot = parts

    is_status = sensor_slot == "_status"
    is_heartbeat = sensor_slot == "_heartbeat"

    body = payload.decode("utf-8") if isinstance(payload, (bytes, bytearray)) else payload
    try:
        data: Dict[str, Any] = json.loads(body)
    except (json.JSONDecodeError, UnicodeDecodeError) as exc:
        log.warning("malformed payload on %s: %s", topic, exc)
        return None

    # Timestamp parsing: accept "...Z" or full ISO-8601.
    raw_ts = data.get("timestamp")
    ts = _parse_timestamp(raw_ts) if isinstance(raw_ts, str) else None
    if ts is None:
        log.warning("ignoring message with missing/invalid timestamp on %s", topic)
        return None

    # Reject samples more than 5 minutes in the future per the contract.
    now = datetime.now(timezone.utc)
    if (ts - now).total_seconds() > 300:
        log.warning("ignoring future-dated sample ts=%s topic=%s", ts.isoformat(), topic)
        return None

    if is_heartbeat:
        return ParsedReading(
            site_slug=site_slug, area_slug=area_slug, asset_slug=asset_slug,
            sensor_slug=sensor_slot, metric="", value=0.0, unit="",
            quality="good", ts=ts, anomaly=None,
            is_status=False, is_heartbeat=True,
        )

    if is_status:
        return ParsedReading(
            site_slug=site_slug, area_slug=area_slug, asset_slug=asset_slug,
            sensor_slug=sensor_slot, metric="", value=0.0, unit="",
            quality="good", ts=ts, anomaly=str(data.get("reason") or "") or None,
            is_status=True, is_heartbeat=False,
        )

    metric = str(data.get("metric") or sensor_slot)
    try:
        value = float(data.get("value"))  # type: ignore[arg-type]
    except (TypeError, ValueError):
        log.warning("ignoring non-numeric value on %s: %r", topic, data.get("value"))
        return None
    unit = str(data.get("unit") or "")
    quality = str(data.get("quality") or "good")
    anomaly = data.get("anomaly")

    return ParsedReading(
        site_slug=site_slug,
        area_slug=area_slug,
        asset_slug=asset_slug,
        sensor_slug=sensor_slot,
        metric=metric,
        value=value,
        unit=unit,
        quality=quality,
        ts=ts,
        anomaly=str(anomaly) if anomaly else None,
        is_status=False,
        is_heartbeat=False,
    )


def _parse_timestamp(raw: str) -> Optional[datetime]:
    try:
        # Python 3.11 fromisoformat accepts the trailing 'Z' from 3.11+, but
        # we normalise just in case.
        text = raw.replace("Z", "+00:00") if raw.endswith("Z") else raw
        ts = datetime.fromisoformat(text)
        if ts.tzinfo is None:
            ts = ts.replace(tzinfo=timezone.utc)
        return ts.astimezone(timezone.utc)
    except ValueError:
        return None


# ---------------------------------------------------------------------------
# Database resolution / persistence
# ---------------------------------------------------------------------------


@dataclass
class _ResolvedAsset:
    asset: Asset
    sensor: Optional[Sensor]
    site_id: UUID


class _AssetCache:
    """Tiny in-process cache for slug -> ORM lookups."""

    def __init__(self) -> None:
        self._by_slug: Dict[Tuple[str, str, str, str], _ResolvedAsset] = {}
        self._lock = threading.Lock()

    def get(self, key: Tuple[str, str, str, str]) -> Optional[_ResolvedAsset]:
        with self._lock:
            return self._by_slug.get(key)

    def put(self, key: Tuple[str, str, str, str], resolved: _ResolvedAsset) -> None:
        with self._lock:
            self._by_slug[key] = resolved

    def invalidate_asset(self, key_prefix: Tuple[str, str, str]) -> None:
        with self._lock:
            for k in list(self._by_slug):
                if k[:3] == key_prefix:
                    self._by_slug.pop(k, None)


def resolve_asset(
    session: Session,
    cache: _AssetCache,
    *,
    site_slug: str,
    area_slug: str,
    asset_slug: str,
    metric: str,
) -> Optional[_ResolvedAsset]:
    """Look up the ``Asset``/``Sensor`` rows for a parsed reading."""
    key = (site_slug, area_slug, asset_slug, metric)
    cached = cache.get(key)
    if cached is not None:
        return cached

    row = session.execute(
        select(Asset, Site.id)
        .join(Area, Asset.area_id == Area.id)
        .join(Site, Area.site_id == Site.id)
        .where(Site.slug == site_slug)
        .where(Area.slug == area_slug)
        .where(Asset.slug == asset_slug)
    ).first()
    if row is None:
        log.debug("unknown asset slugs %s/%s/%s", site_slug, area_slug, asset_slug)
        return None
    asset, site_id = row

    sensor = None
    if metric:
        sensor = session.execute(
            select(Sensor).where(Sensor.asset_id == asset.id).where(Sensor.metric == metric)
        ).scalar_one_or_none()

    resolved = _ResolvedAsset(asset=asset, sensor=sensor, site_id=site_id)
    cache.put(key, resolved)
    return resolved


def write_telemetry(
    session: Session,
    *,
    reading: ParsedReading,
    resolved: _ResolvedAsset,
) -> bool:
    """Insert one telemetry row. Returns True on success, False on dup."""
    if resolved.sensor is None:
        return False
    row = Telemetry(
        ts=reading.ts,
        company_id=resolved.asset.area_id,  # placeholder if migration uses company_id
        site_id=resolved.site_id,
        area_id=resolved.asset.area_id,
        asset_id=resolved.asset.id,
        sensor_id=resolved.sensor.id,
        metric=reading.metric,
        value=reading.value,
        unit=reading.unit,
        quality=reading.quality if reading.quality in ("good", "uncertain", "bad") else "good",
    )
    session.add(row)
    try:
        session.flush()
    except IntegrityError:
        session.rollback()
        return False
    return True


def maybe_open_alarm(
    session: Session,
    *,
    reading: ParsedReading,
    resolved: _ResolvedAsset,
) -> Optional[AlarmDecision]:
    """Run the alarm engine for a reading and persist if it fires."""
    decision = evaluate(
        asset_type=resolved.asset.asset_type,
        metric=reading.metric,
        value=reading.value,
        ts=reading.ts,
    )
    if decision is None:
        return None
    open_alarm_if_new(
        session,
        asset=resolved.asset,
        sensor=resolved.sensor,
        site_id=resolved.site_id,
        decision=decision,
        opened_at=reading.ts,
    )
    return decision


# ---------------------------------------------------------------------------
# End-to-end message handler
# ---------------------------------------------------------------------------


@dataclass
class ProcessResult:
    """What ``process_message`` produced for callers to broadcast.

    Any of the fields may be ``None`` if not applicable (e.g. heartbeats
    yield an empty result, status messages produce only ``status_event``).
    """

    reading: Optional[ParsedReading] = None
    decision: Optional[AlarmDecision] = None
    telemetry_event: Optional[Dict[str, Any]] = None
    status_event: Optional[Dict[str, Any]] = None
    alarm_event: Optional[Dict[str, Any]] = None
    asset_id: Optional[UUID] = None
    sensor_id: Optional[UUID] = None


def _build_telemetry_event(reading: ParsedReading, resolved: _ResolvedAsset) -> Dict[str, Any]:
    return {
        "type": "telemetry",
        "asset_id": str(resolved.asset.id),
        "sensor_id": str(resolved.sensor.id) if resolved.sensor is not None else None,
        "metric": reading.metric,
        "value": reading.value,
        "unit": reading.unit,
        "quality": reading.quality,
        "ts": reading.ts.isoformat().replace("+00:00", "Z"),
    }


def _build_status_event(reading: ParsedReading, resolved: _ResolvedAsset) -> Dict[str, Any]:
    return {
        "type": "status",
        "asset_id": str(resolved.asset.id),
        "status": reading.anomaly or "online",
        "reason": reading.anomaly or "heartbeat_ok",
        "ts": reading.ts.isoformat().replace("+00:00", "Z"),
    }


def _build_alarm_event(decision: AlarmDecision, resolved: _ResolvedAsset, ts: datetime) -> Dict[str, Any]:
    return {
        "type": "alarm",
        "asset_id": str(resolved.asset.id),
        "sensor_id": str(resolved.sensor.id) if resolved.sensor is not None else None,
        "code": decision.code,
        "severity": decision.severity,
        "message": decision.message,
        "ts": ts.isoformat().replace("+00:00", "Z"),
    }


def process_message(
    *,
    topic: str,
    payload: bytes | str,
    cache: _AssetCache,
    session_factory: Callable[[], Session] = SessionLocal,
) -> ProcessResult:
    """Parse + persist + evaluate one MQTT message.

    Returns a :class:`ProcessResult` carrying any events the caller should
    broadcast over WebSocket. An empty result means "nothing to do" (e.g.
    a heartbeat or an unknown asset).
    """
    result = ProcessResult()
    reading = parse_message(topic, payload)
    if reading is None or reading.is_heartbeat:
        return result
    result.reading = reading

    with session_factory() as session:  # type: ignore[call-arg]
        try:
            resolved = resolve_asset(
                session,
                cache,
                site_slug=reading.site_slug,
                area_slug=reading.area_slug,
                asset_slug=reading.asset_slug,
                metric=reading.metric,
            )
            if resolved is None:
                return result

            result.asset_id = resolved.asset.id
            if resolved.sensor is not None:
                result.sensor_id = resolved.sensor.id

            if reading.is_status:
                # Status updates flow straight to the WS layer; no telemetry
                # row, no alarm evaluation here.
                result.status_event = _build_status_event(reading, resolved)
                return result

            if reading.quality == "bad":
                log.info("dropping bad-quality reading topic=%s", topic)
                return result

            wrote = write_telemetry(session, reading=reading, resolved=resolved)
            if wrote:
                result.telemetry_event = _build_telemetry_event(reading, resolved)
                decision = maybe_open_alarm(session, reading=reading, resolved=resolved)
                if decision is not None:
                    result.decision = decision
                    result.alarm_event = _build_alarm_event(decision, resolved, reading.ts)
            session.commit()
            return result
        except SQLAlchemyError:
            log.exception("DB error processing message topic=%s", topic)
            session.rollback()
            return result


# ---------------------------------------------------------------------------
# Background task wrapper
# ---------------------------------------------------------------------------


def _new_paho_client(client_id: str) -> Any:
    """Create a paho ``Client`` that works on both 1.x and 2.x.

    paho 2.0 introduced ``CallbackAPIVersion`` and the legacy positional
    signature emits a ``DeprecationWarning``. We feature-detect and fall
    back so the consumer works against either pinned version.
    """
    if mqtt is None:
        raise RuntimeError("paho-mqtt is required to run MqttConsumer")
    callback_api_version = getattr(mqtt, "CallbackAPIVersion", None)
    if callback_api_version is not None:
        return mqtt.Client(
            callback_api_version=callback_api_version.VERSION1,
            client_id=client_id,
            clean_session=True,
        )
    return mqtt.Client(client_id=client_id, clean_session=True)


class MqttConsumer:
    """Long-running MQTT subscriber.

    Runs paho's network loop in its own thread (paho's preferred pattern)
    and pushes parsed messages onto a bounded ``asyncio.Queue`` consumed by
    an asyncio task. This keeps the network thread responsive while the
    DB writes run in the event loop.
    """

    def __init__(
        self,
        *,
        host: Optional[str] = None,
        port: Optional[int] = None,
        username: Optional[str] = None,
        password: Optional[str] = None,
        client_id: str = "energyops-backend",
        broadcast: Optional[Callable[[Dict[str, Any]], Awaitable[None]]] = None,
    ) -> None:
        if mqtt is None:
            raise RuntimeError("paho-mqtt is required to run MqttConsumer")
        self._host = host or _env("MQTT_HOST", "mosquitto")
        self._port = int(port if port is not None else _env_int("MQTT_PORT", 1883))
        self._username = username if username is not None else _env_optional("MQTT_USERNAME")
        self._password = password if password is not None else _env_optional("MQTT_PASSWORD")
        self._client_id = client_id
        self._broadcast = broadcast
        self._cache = _AssetCache()
        self._queue: asyncio.Queue[Tuple[str, bytes]] = asyncio.Queue(maxsize=1000)
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._client: Any = None
        self._task: Optional[asyncio.Task[None]] = None
        self._stop_event = asyncio.Event()

    # -- lifecycle --------------------------------------------------------

    async def start(self) -> None:
        self._loop = asyncio.get_running_loop()
        self._client = _new_paho_client(self._client_id)
        if self._username:
            self._client.username_pw_set(self._username, self._password or "")
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        self._client.reconnect_delay_set(min_delay=1, max_delay=30)
        # connect_async + loop_start lets paho handle reconnects internally,
        # so a temporarily unavailable broker won't crash the API.
        try:
            self._client.connect_async(self._host, self._port, keepalive=30)
        except Exception:  # noqa: BLE001
            log.warning(
                "mqtt initial connect_async failed host=%s port=%d; paho will retry",
                self._host, self._port,
            )
        self._client.loop_start()
        self._task = asyncio.create_task(self._consume(), name="mqtt-consumer")
        log.info("mqtt consumer started host=%s port=%d", self._host, self._port)

    async def stop(self) -> None:
        self._stop_event.set()
        if self._client is not None:
            try:
                self._client.loop_stop()
                self._client.disconnect()
            except Exception:  # pragma: no cover - best-effort
                log.exception("error stopping mqtt client")
        if self._task is not None:
            self._task.cancel()
            try:
                await self._task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001
                pass
        log.info("mqtt consumer stopped")

    # -- paho callbacks ---------------------------------------------------

    def _on_connect(self, client, userdata, flags, rc) -> None:  # noqa: ANN001
        if rc == 0:
            client.subscribe(TOPIC_FILTER, qos=1)
            log.info("mqtt subscribed filter=%s", TOPIC_FILTER)
        else:
            log.warning("mqtt connect failed rc=%s", rc)

    def _on_message(self, client, userdata, msg) -> None:  # noqa: ANN001
        # Hand off to the asyncio loop without blocking the network thread.
        if self._loop is None or self._loop.is_closed():
            return
        try:
            self._loop.call_soon_threadsafe(self._queue.put_nowait, (msg.topic, msg.payload))
        except asyncio.QueueFull:
            log.warning("mqtt queue full, dropping topic=%s", msg.topic)

    # -- consumer task ----------------------------------------------------

    async def _consume(self) -> None:
        while not self._stop_event.is_set():
            try:
                topic, payload = await asyncio.wait_for(self._queue.get(), timeout=1.0)
            except asyncio.TimeoutError:
                continue
            try:
                # Run blocking SQLAlchemy work in a thread so we don't stall the loop.
                result = await asyncio.to_thread(
                    process_message,
                    topic=topic,
                    payload=payload,
                    cache=self._cache,
                )
                if self._broadcast is None:
                    continue
                for event in (result.telemetry_event, result.status_event, result.alarm_event):
                    if event is not None:
                        try:
                            await self._broadcast(event)
                        except Exception:  # noqa: BLE001
                            log.exception("ws broadcast failed type=%s", event.get("type"))
            except Exception:  # noqa: BLE001
                log.exception("error processing mqtt message topic=%s", topic)


# ---------------------------------------------------------------------------
# Env helpers (kept tiny; backend/app/config exposes the canonical settings
# but those are pydantic and tied to the .env file. The consumer needs
# broker connection details that live alongside the simulator's env vars).
# ---------------------------------------------------------------------------


def _env(name: str, default: str) -> str:
    import os
    value = os.getenv(name)
    return value if value not in (None, "") else default


def _env_int(name: str, default: int) -> int:
    import os
    raw = os.getenv(name)
    if raw in (None, ""):
        return default
    try:
        return int(raw)
    except ValueError:
        return default


def _env_optional(name: str) -> Optional[str]:
    import os
    raw = os.getenv(name)
    return raw if raw not in (None, "") else None


