"""Tests for the topic builder and JSON payload shape."""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone

from simulator.assets import (
    asset_channel_topic,
    build_payload,
    default_assets,
    Reading,
    topic_for,
)


TOPIC_RE = re.compile(r"^industrial/[a-z0-9-]+/[a-z0-9-]+/[a-z0-9-]+/[a-z0-9_-]+$")


def _make_reading():
    asset = default_assets()[0]  # pump
    return Reading(asset=asset, sensor=asset.sensors[0], value=42.5, quality="good")


def test_topic_for_telemetry_matches_brief_format():
    r = _make_reading()
    topic = topic_for(r, root="industrial")
    assert topic == "industrial/kuantan-plant/utilities/pump-p-101/power_kw"
    assert TOPIC_RE.match(topic)


def test_topic_for_status_uses_underscore_slot():
    asset = default_assets()[0]
    topic = asset_channel_topic(asset, root="industrial", channel="status")
    assert topic == "industrial/kuantan-plant/utilities/pump-p-101/_status"
    assert TOPIC_RE.match(topic)


def test_payload_has_required_fields():
    r = _make_reading()
    ts = datetime(2026, 5, 27, 10, 15, 30, tzinfo=timezone.utc)
    payload = build_payload(r, company_name="Demo Industrial Holdings", ts=ts)
    expected_keys = {
        "timestamp", "company", "site", "area", "asset",
        "sensor", "metric", "value", "unit", "quality", "anomaly",
    }
    assert set(payload) == expected_keys
    assert payload["timestamp"].endswith("Z")
    assert payload["company"] == "Demo Industrial Holdings"
    assert payload["site"] == "Kuantan Plant"
    assert payload["asset"] == "Pump P-101"
    assert payload["metric"] == "power_kw"
    assert payload["unit"] == "kW"
    assert payload["value"] == 42.5
    assert payload["quality"] == "good"
    assert payload["anomaly"] is None


def test_payload_roundtrips_via_json():
    r = _make_reading()
    ts = datetime(2026, 5, 27, 10, 15, 30, tzinfo=timezone.utc)
    payload = build_payload(r, company_name="Demo Industrial Holdings", ts=ts)
    parsed = json.loads(json.dumps(payload))
    assert parsed == payload
