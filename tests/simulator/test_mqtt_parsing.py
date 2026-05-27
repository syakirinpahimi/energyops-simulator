"""Tests for the MQTT consumer's pure parsing layer.

We import only the pure helpers to avoid pulling in SQLAlchemy at import
time when the backend isn't installed locally.
"""
from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
if str(BACKEND) not in sys.path:
    sys.path.insert(0, str(BACKEND))

pytest.importorskip("sqlalchemy", reason="backend deps not installed")

from app.services.mqtt_consumer import parse_message, parse_topic  # noqa: E402


def _payload(**overrides):
    base = {
        "timestamp": "2026-05-20T13:00:00Z",
        "company": "Demo Industrial Holdings",
        "site": "Kuantan Plant",
        "area": "Utilities",
        "asset": "Pump P-101",
        "sensor": "power_kw",
        "metric": "power_kw",
        "value": 42.5,
        "unit": "kW",
        "quality": "good",
        "anomaly": None,
    }
    base.update(overrides)
    return json.dumps(base).encode("utf-8")


def test_parse_topic_returns_five_parts():
    parts = parse_topic("industrial/kuantan-plant/utilities/pump-p-101/power_kw")
    assert parts == ("industrial", "kuantan-plant", "utilities", "pump-p-101", "power_kw")


def test_parse_topic_rejects_wrong_shape():
    assert parse_topic("industrial/kuantan-plant/utilities") is None
    assert parse_topic("foo/bar/baz/qux/quux/extra") is None


def test_parse_message_returns_normalised_reading():
    reading = parse_message(
        "industrial/kuantan-plant/utilities/pump-p-101/power_kw",
        _payload(),
    )
    assert reading is not None
    assert reading.site_slug == "kuantan-plant"
    assert reading.metric == "power_kw"
    assert reading.value == 42.5
    assert reading.unit == "kW"
    assert reading.quality == "good"
    assert reading.is_status is False
    assert reading.is_heartbeat is False


def test_parse_message_recognises_status_topic():
    payload = json.dumps({
        "timestamp": "2026-05-20T13:00:00Z",
        "asset": "Pump P-101",
        "site": "Kuantan Plant",
        "status": "fault",
        "reason": "vibration_spike",
    }).encode("utf-8")
    reading = parse_message("industrial/kuantan-plant/utilities/pump-p-101/_status", payload)
    assert reading is not None
    assert reading.is_status is True
    assert reading.anomaly == "vibration_spike"


def test_parse_message_recognises_heartbeat_topic():
    payload = json.dumps({
        "timestamp": "2026-05-20T13:00:00Z",
        "asset": "Pump P-101",
    }).encode("utf-8")
    reading = parse_message("industrial/kuantan-plant/utilities/pump-p-101/_heartbeat", payload)
    assert reading is not None
    assert reading.is_heartbeat is True


def test_parse_message_rejects_malformed_json():
    assert parse_message("industrial/a/b/c/d", b"not-json") is None


def test_parse_message_rejects_missing_timestamp():
    bad = json.dumps({"value": 1.0}).encode("utf-8")
    assert parse_message("industrial/a/b/c/d", bad) is None


def test_parse_message_accepts_iso_with_offset():
    payload = _payload(timestamp="2026-05-20T13:00:00+00:00")
    reading = parse_message("industrial/kuantan-plant/utilities/pump-p-101/power_kw", payload)
    assert reading is not None
    assert reading.ts == datetime(2026, 5, 20, 13, 0, tzinfo=timezone.utc)


def test_parse_message_rejects_far_future_timestamp():
    payload = _payload(timestamp="2099-01-01T00:00:00Z")
    assert parse_message("industrial/kuantan-plant/utilities/pump-p-101/power_kw", payload) is None
