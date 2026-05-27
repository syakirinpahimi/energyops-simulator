# Simulator

Owner track: `simulator` (see `docs/AGENT_WORKFLOW.md`).

A Python service that publishes synthetic but realistic telemetry to MQTT for every seeded asset. It exists so the dashboard has live data without real plant equipment.

> **Topic shape:** `industrial/{site}/{area}/{asset}/{sensor}` (five
> segments). Status / heartbeat reuse the sensor slot with reserved
> `_status` / `_heartbeat` names so a single backend wildcard
> (`industrial/+/+/+/+`) matches everything. The full contract lives in
> `docs/API_CONTRACT.md` § MQTT topic conventions, and the decision is
> recorded in `docs/adr/0001-mqtt-topic-contract.md`.

## Quick start

```bash
# from repo root
cp .env.example .env
docker compose up -d mosquitto
pip install -r simulator/requirements.txt

# Smoke run: 10 ticks with the in-memory publisher, no broker required.
python -m simulator.main --smoke --seed 42

# Live run against the broker, every 5s, with a deterministic seed.
SIM_RANDOM_SEED=42 python -m simulator.main
```

## Environment variables

| Var                     | Default       | Notes                                            |
|-------------------------|---------------|--------------------------------------------------|
| `MQTT_HOST`             | `localhost`   | Broker host.                                     |
| `MQTT_PORT`             | `1883`        | Broker port.                                     |
| `MQTT_USERNAME`         | _(unset)_     | Optional broker auth.                            |
| `MQTT_PASSWORD`         | _(unset)_     | Optional broker auth.                            |
| `SIM_TICK_SECONDS`      | `5`           | Publish interval per asset.                      |
| `SIM_TICK_JITTER`       | `0`           | ± seconds of jitter applied to each sleep.       |
| `SIM_FAULT_PROBABILITY` | `0.01`        | Per-tick chance of injecting an anomaly.         |
| `SIM_RANDOM_SEED`       | _(unset)_     | Seed for deterministic demos.                    |
| `SIM_TOPIC_ROOT`        | `industrial`  | Topic prefix.                                    |
| `LOG_LEVEL`             | `INFO`        | Standard logging level.                          |
| `SIM_LOG_JSON`          | `false`       | Emit JSON logs for ingestion in dashboards.      |
| `SIM_MAX_TICKS`         | _(unset)_     | Stop after N ticks (useful in CI).               |
| `SIM_MAX_SECONDS`       | _(unset)_     | Stop after N seconds (useful in CI).             |

## Layout (current)

```
simulator/
├── __init__.py
├── main.py            # entrypoint + CLI (--smoke, --once, --ticks, --seed)
├── config.py          # env-driven Settings dataclass
├── assets.py          # five demo assets, generators, anomaly catalogue
├── requirements.txt
├── Dockerfile
└── README.md
```

## Anomalies

| Asset                  | Anomaly tag           | Effect                                                   |
|------------------------|-----------------------|----------------------------------------------------------|
| Pump P-101             | `vibration_spike`     | Vibration jumps over the 8 mm/s warning threshold.       |
| Air Compressor C-201   | `high_temperature`    | Temperature climbs over 95 °C.                           |
| HVAC Chiller CH-1      | `high_power_draw`     | Power draw exceeds 220 kW.                               |
| Solar Inverter INV-01  | `low_output_daytime`  | Output drops to ~5 kW during the simulated solar window. |
| Main Grid Meter GM-01  | `voltage_dip`         | Voltage drops below 210 V.                               |

Each anomaly is held for 3–6 ticks so threshold rules see a sustained breach.

## Testing

```bash
pip install pytest
pytest tests/simulator
```

Tests live in `tests/simulator/` and cover:

- the asset catalogue and per-tick generators (`test_assets.py`)
- topic strings and JSON payload shape (`test_topics.py`)
- the runner end-to-end with an in-memory publisher (`test_runner.py`)
- the backend alarm engine threshold rules (`test_alarm_engine.py`)
- the backend MQTT consumer's parsing layer (`test_mqtt_parsing.py`)

## MQTT publishing rules

- Topic format: `industrial/{site}/{area}/{asset}/{sensor}` (five
  segments). Use the asset's slug chain, never the UUID, in topics.
- QoS 1 across the board.
- `retain=True` for `_status` so the latest state survives broker
  restarts.
- `retain=False` for telemetry and `_heartbeat`.
- Reconnect with exponential backoff on broker disconnects, capped at
  30s (handled by `paho-mqtt`'s `reconnect_delay_set`).

## Out of scope (intentionally)

The MVP simulator stops at the five demo assets and the anomaly catalogue
above. The list below is captured so reviewers can see the deliberate cut
lines:

- Replaying recorded plant traces.
- Multi-broker / TLS configurations.
- Coordinated cascading faults (e.g. one inverter trip causing a
  substation alarm).
- A web UI for tuning fault rates at runtime.
