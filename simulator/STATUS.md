# Simulator status

Last updated: 2026-05-27 by simulator session

## Done

- `simulator/config.py` -- env-driven `Settings` dataclass, `configure_logging`.
- `simulator/assets.py` -- five demo assets (pump, compressor, chiller, inverter, meter), per-tick generators with realistic curves and drift, anomaly catalogue, topic + payload helpers.
- `simulator/main.py` -- `SimulatorRunner`, `MqttPublisher`/`InMemoryPublisher`, CLI with `--smoke`, `--once`, `--ticks`, `--seed`, signal handling, jittered sleep.
- `simulator/requirements.txt`, `simulator/Dockerfile`, `simulator/__init__.py` -- packaging.
- `simulator/README.md` -- usage, env vars, anomaly map, divergence note.
- `backend/app/services/alarm_engine.py` -- threshold rule table aligned with the simulator anomalies, daylight gate for inverter, idempotent OPEN-alarm helper using the partial unique index.
- `backend/app/services/mqtt_consumer.py` -- pure parser (`parse_message`/`parse_topic`), DB-backed asset resolver with cache, `process_message`, async `MqttConsumer` background task.
- `tests/simulator/test_assets.py`, `test_topics.py`, `test_runner.py`, `test_alarm_engine.py`, `test_mqtt_parsing.py`.

## In progress / partial

- The `MqttConsumer` is wired but not started anywhere; the backend `lifespan` in `app/main.py` still has a `TODO(backend): start MQTT subscriber background task here.` Wiring it in belongs to the backend track per `docs/AGENT_WORKFLOW.md`.

## TODO (next session)

- Backend track: instantiate `MqttConsumer` in `app/main.py` lifespan and pass `ws_hub.broadcast` as the `broadcast` callback so live telemetry surfaces on `/ws/telemetry`.
- Add `tests/backend/test_mqtt_persistence.py` once the backend test fixtures grow a Postgres harness.

## Open questions for the architect

- ~~Topic shape: brief says `industrial/{site}/{area}/{asset}/{sensor}` (5 segments), `docs/API_CONTRACT.md` says `energyops/{company}/{site}/{area}/{asset}/{channel}` (6 segments).~~ **Resolved 2026-05-27** by `docs/adr/0001-mqtt-topic-contract.md`: the five-segment `industrial/...` shape is the canonical contract. `docs/API_CONTRACT.md`, `README.md`, and the simulator config comments have been updated to match.
