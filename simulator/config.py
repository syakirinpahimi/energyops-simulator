"""Configuration for the industrial telemetry simulator.

Loads environment variables with sensible defaults and exposes a single
``Settings`` instance for the rest of the simulator to consume. Kept
deliberately small and dependency-free so unit tests can import it without
pulling in MQTT or HTTP libraries.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from typing import Optional


def _env_str(key: str, default: str) -> str:
    value = os.getenv(key)
    if value is None or value == "":
        return default
    return value


def _env_int(key: str, default: int) -> int:
    raw = os.getenv(key)
    if raw is None or raw == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{key} must be an integer, got {raw!r}") from exc


def _env_float(key: str, default: float) -> float:
    raw = os.getenv(key)
    if raw is None or raw == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{key} must be a float, got {raw!r}") from exc


def _env_optional_int(key: str) -> Optional[int]:
    raw = os.getenv(key)
    if raw is None or raw == "":
        return None
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{key} must be an integer, got {raw!r}") from exc


def _env_bool(key: str, default: bool) -> bool:
    raw = os.getenv(key)
    if raw is None or raw == "":
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


@dataclass(frozen=True)
class Settings:
    """Runtime configuration for the simulator.

    All fields are populated from environment variables. Defaults are tuned
    for a local ``docker compose`` run.
    """

    # MQTT broker
    mqtt_host: str = "localhost"
    mqtt_port: int = 1883
    mqtt_username: Optional[str] = None
    mqtt_password: Optional[str] = None
    mqtt_client_id: str = "energyops-simulator"
    mqtt_keepalive: int = 30

    # Topic conventions
    # ``industrial/{site}/{area}/{asset}/{sensor}`` for telemetry, with
    # status / heartbeat reusing the sensor slot via reserved
    # underscore-prefixed names (``_status``/``_heartbeat``) so the
    # backend wildcard ``industrial/+/+/+/+`` matches every published
    # topic. The decision is recorded in
    # ``docs/adr/0001-mqtt-topic-contract.md``.
    topic_root: str = "industrial"

    # Tick / fault behaviour
    tick_seconds: float = 5.0
    tick_jitter: float = 0.0  # 0 means deterministic, >0 spreads each tick by ±jitter
    fault_probability: float = 0.01

    # Reproducibility
    random_seed: Optional[int] = None

    # Logging
    log_level: str = "INFO"
    log_json: bool = False

    # Lifetime controls used by the smoke command
    max_ticks: Optional[int] = None
    max_seconds: Optional[float] = None

    @property
    def display_company(self) -> str:
        """Human-readable company name used in telemetry payloads."""
        return "Demo Industrial Holdings"


def load_settings() -> Settings:
    """Build a ``Settings`` instance from the current environment."""

    return Settings(
        mqtt_host=_env_str("MQTT_HOST", "localhost"),
        mqtt_port=_env_int("MQTT_PORT", 1883),
        mqtt_username=os.getenv("MQTT_USERNAME") or None,
        mqtt_password=os.getenv("MQTT_PASSWORD") or None,
        mqtt_client_id=_env_str("SIM_MQTT_CLIENT_ID", "energyops-simulator"),
        mqtt_keepalive=_env_int("SIM_MQTT_KEEPALIVE", 30),
        topic_root=_env_str("SIM_TOPIC_ROOT", "industrial"),
        tick_seconds=_env_float("SIM_TICK_SECONDS", 5.0),
        tick_jitter=_env_float("SIM_TICK_JITTER", 0.0),
        fault_probability=_env_float("SIM_FAULT_PROBABILITY", 0.01),
        random_seed=_env_optional_int("SIM_RANDOM_SEED"),
        log_level=_env_str("LOG_LEVEL", "INFO").upper(),
        log_json=_env_bool("SIM_LOG_JSON", False),
        max_ticks=_env_optional_int("SIM_MAX_TICKS"),
        max_seconds=_env_optional_int("SIM_MAX_SECONDS"),
    )


def configure_logging(settings: Settings) -> logging.Logger:
    """Configure the root logger and return the simulator logger."""

    level = getattr(logging, settings.log_level, logging.INFO)
    handler = logging.StreamHandler()
    if settings.log_json:
        handler.setFormatter(logging.Formatter(
            '{"ts":"%(asctime)s","level":"%(levelname)s","name":"%(name)s",'
            '"msg":"%(message)s"}'
        ))
    else:
        handler.setFormatter(logging.Formatter(
            "%(asctime)s %(levelname)-7s %(name)s %(message)s"
        ))
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    return logging.getLogger("simulator")
