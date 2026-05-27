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

## Responsibilities

- On startup, fetch the asset/sensor list from the backend (`GET /api/v1/assets`). If the backend is unreachable, fall back to a local `assets.yaml` for development.
- For each sensor, publish a `telemetry` message every `SIM_TICK_SECONDS`.
- Publish a `heartbeat` per asset every 30 seconds.
- With probability `SIM_FAULT_PROBABILITY` per tick per asset, emit a fault: `alarm` + `status` transition.
- Recover from faults after a randomised dwell (30–120s): another `status` and an alarm-clear pattern.

## Stack

- Python 3.11
- `paho-mqtt`
- `pydantic` for payload validation
- `httpx` for the asset bootstrap call
- `PyYAML` for the local fallback file

## Suggested layout

```
simulator/
├── Dockerfile
├── README.md            # this file
├── STATUS.md            # update before ending each session
├── pyproject.toml
├── app/
│   ├── __init__.py
│   ├── main.py          # entrypoint, runs the tick loop
│   ├── config.py        # pydantic-settings Settings class
│   ├── bootstrap.py     # fetch asset list (REST or local YAML)
│   ├── publisher.py     # paho-mqtt wrapper, retain/QoS rules
│   ├── generators/      # one generator per asset_type
│   │   ├── __init__.py
│   │   ├── boiler.py
│   │   ├── compressor.py
│   │   ├── inverter.py
│   │   ├── chiller.py
│   │   ├── ups.py
│   │   ├── pdu.py
│   │   └── meter.py
│   ├── faults.py        # fault injection + recovery state machine
│   └── topics.py        # build topic strings per the contract
└── assets.example.yaml  # local fallback used when backend is offline
```

## Local development

```bash
cd simulator
python -m venv .venv && .venv/Scripts/activate
pip install -e .
# Backend + broker should be running:
docker compose up -d postgres mosquitto backend
python -m app.main
```

You should see telemetry flowing in the broker. Check with `mosquitto_sub`:

```bash
mosquitto_sub -h localhost -t 'industrial/#' -v
```

## Generator design

Each generator is a small pure function:

```python
def step(asset: Asset, t: datetime, state: dict) -> list[Reading]:
    ...
```

- `state` is a per-asset dict the runner passes back in on the next tick (for things like a slow temperature ramp).
- Output is one `Reading` per sensor for that tick.

Curves to aim for (junior-friendly, not physically accurate):

- **boiler**: power 60–95% of rated with slow drift; temperature follows power with a lag; pressure tracks temperature.
- **compressor**: duty-cycle pattern (on for 5–10 min, off for 1–2 min); vibration spikes briefly on startup.
- **inverter**: solar daylight curve, zero before sunrise/after sunset; DC voltage roughly constant; AC voltage follows production.
- **chiller**: smooth diurnal load with small noise; supply 6–8°C, return 12–14°C.
- **ups**: load mostly flat; battery 95–100% under normal; input voltage ~230V with 1% noise.
- **pdu / meter**: aggregate of upstream loads; energy_kwh increments monotonically.

Add ±gaussian noise (1–5% of value) to every reading so charts look organic.

## Fault injection

On a fault:

1. Pick a code appropriate for the asset type (`TEMP_HIGH`, `OVERLOAD`, `COMM_LOST`, `LOW_BATTERY`, ...).
2. Publish an `alarm` message with `severity` weighted toward `warning` (70%), `critical` (25%), `info` (5%).
3. Publish a `status` message: `fault` for hard faults, `online` stays for soft warnings.
4. Bias generator output for the fault duration (e.g. boiler temperature climbs above threshold during `TEMP_HIGH`).
5. After dwell, publish a recovery `status` of `online`.

Alarm clearing is handled by the backend (operator ack/resolve), not the simulator. The simulator only opens alarms.

## MQTT publishing rules

- Topic format: see `docs/API_CONTRACT.md` § MQTT topic conventions. Use the asset's slug chain, never the UUID, in topics.
- QoS 1 for all channels.
- `retain=True` for `status` (latest state should survive broker restarts).
- `retain=False` for `telemetry`, `alarm`, `heartbeat`.
- Reconnect with exponential backoff on broker disconnects; cap at 30s.

## Configuration

Environment variables (see `.env.example`):

- `MQTT_HOST`, `MQTT_PORT`, `MQTT_USERNAME`, `MQTT_PASSWORD`
- `SIM_TICK_SECONDS` — default 5
- `SIM_FAULT_PROBABILITY` — default 0.01
- `SIM_BACKEND_URL` — for the asset bootstrap, default `http://backend:8000`
- `SIM_ASSETS_FILE` — fallback path, default `./assets.yaml`

## Testing

- Pure-function tests for each generator (deterministic with a fixed seed).
- A topic-builder test that asserts strings match the contract regex.
- An end-to-end smoke test that runs the publisher against a local broker for ~10s and asserts at least N messages were received.

## Definition of done

- Every seeded asset emits the sensors listed in `docs/DATA_MODEL.md` § Sensor template per asset type.
- Topic strings exactly match the contract.
- Fault rate is within ±20% of `SIM_FAULT_PROBABILITY` over a 10-minute run.
- No `TODO(simulator)` markers remain.

## Out of scope (leave as `TODO(future)`)

- Replaying recorded plant traces
- Multi-broker / TLS configurations
- Coordinated cascading faults (e.g. one inverter trip causing a substation alarm)
- Web UI for tuning fault rates at runtime
