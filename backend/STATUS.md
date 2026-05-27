# Backend status

Last updated: 2026-05-27  by  reports/alarms/audit polishing session

## Done (data slice, prior session)

- Project skeleton (`requirements.txt`, `alembic.ini`).
- `app/config.py`, `app/db.py`, `app/security.py` (password hashing).
- `app/models.py` covering every table in `docs/DATA_MODEL.md` plus
  `alarm_rules` and `TelemetryReading` alias.
- Alembic baseline migration `0001_initial.py` (extensions, enums, tables,
  hypertable, partial unique index, `telemetry_5m` continuous aggregate).
- `scripts/seed.py` + `scripts/reset_db.py`, idempotent demo seed.
- `tests/db/test_smoke.py` smoke test.
- `services/alarm_engine.py` and `services/mqtt_consumer.py` for the live
  ingestion path.

## Done (FastAPI app, this session)

- `app/main.py` - app factory, CORS, lifespan, JSON error envelope handlers
  for `HTTPException`, `RequestValidationError`, `OperationalError`,
  `SQLAlchemyError`. App boots even when the DB is unreachable.
- `app/security.py` extended with `create_access_token` / `decode_access_token`
  (HS256, expiry from settings, role+company claims merged via
  `extra_claims`).
- `app/deps.py` - `get_current_user` (Bearer JWT), `require_role(...)` and
  `roles_at_least(level)` factories with the role hierarchy
  `operator < engineer < manager < admin`.
- `app/schemas.py` - Pydantic v2 schemas for every contract response,
  including the audit row mapper that translates the DB column names
  (`timestamp`/`user_id`/`entity_type`/`entity_id`/`details_json`) into
  the contract names (`ts`/`actor_id`/`target_type`/`target_id`/`metadata`).
- `app/services/audit.py` - `write_audit(...)` writer used by login + alarm
  ack so the audit trail is consistent.
- `app/services/ws_hub.py` - in-memory WebSocket hub with locked broadcast.
- `app/routes/`:
  - `health.py` - `GET /health`
  - `auth.py` - `POST /auth/login`, `GET /auth/me`
  - `hierarchy.py` - `GET /companies|/sites|/areas|/assets|/sensors`,
    `GET /assets/{id}`, `GET /assets/{id}/sensors`,
    `DELETE /assets/{id}` (manager+).
  - `telemetry.py` - `GET /telemetry/latest` (grouped by asset),
    `GET /telemetry/history` (epoch-floor bucketing, works on plain PG).
  - `alarms.py` - `GET /alarms`, `GET /alarms/{id}`,
    `POST /alarms/{id}/acknowledge` (alias `/ack`),
    `POST /alarms/{id}/resolve` (engineer+). Ack writes audit row.
    Responses are hydrated with `asset_name`, `sensor_name`,
    `triggered_value`, `threshold_value`, and `acked_by_email` so the
    frontend table has everything in one round trip.
  - `reports.py` - manager+:
      `GET /reports/energy/summary` (JSON cards: total kWh, peak kW,
      top 5 consumers, alarm counts),
      `GET /reports/energy.csv` (per-reading rows: timestamp, site,
      area, asset, sensor, metric, value, unit; capped at 100k rows),
      `GET /reports/energy.pdf` (single-page PDF with title
      "Industrial EnergyOps Energy Report", site/date-range/generated
      timestamp, total kWh, peak kW, top assets, alarm summary).
    All three accept `site_id`, `asset_id`, `start`, `end` filters.
  - `audit.py` - `GET /audit-log` (alias `/audit`), engineer+.
  - `ws.py` - `WS /ws/telemetry` and `/stream/telemetry`, JWT in query,
    30s heartbeat ping, registered with the hub.
- All routes are also mounted under `/api/v1/*` to match the frozen contract.
- `app/seed.py` is a thin shim that re-exports `scripts.seed.run` so
  `python -m app.seed` works as documented.
- Tests:
  - `tests/test_smoke_app.py` - DB-free smoke (health, openapi, 401s).
  - `tests/test_auth.py`, `test_hierarchy.py`, `test_alarms.py`,
    `test_reports.py` - integration tests gated behind `RUN_DB_TESTS=1`
    (or auto-detect of a reachable DB).
  - `test_alarms.py::test_acknowledge_alarm_writes_audit_log` now
    asserts the `audit_log` row count grows by exactly one and that
    the row carries the alarm id, actor email, and ack note.

## Test run

```
6 passed, 17 skipped
```

The 17 skipped tests need a reachable Postgres + seed; they auto-run when
`RUN_DB_TESTS=1` is set or the DB is reachable.

## TODO (next session)

- `DONE`: `services.mqtt_consumer.MqttConsumer` is wired into
  `app.main.lifespan` and receives `broadcast=hub.broadcast`. Toggle with
  `MQTT_ENABLED=0` to skip the consumer (used by unit tests). Lifespan is
  best-effort: a missing broker logs a warning and the API still serves.
- `TODO(backend)`: WS subscribe/unsubscribe filtering. The hub currently
  broadcasts to everyone; the contract supports per-asset/per-site filters.
- `TODO(backend)`: write-path endpoints (`POST /sites`, `POST /assets`,
  `PATCH /assets/{id}`, etc.) - read endpoints already cover the MVP UI.
- `TODO(backend)`: replace synthetic energy aggregation in
  `routes/reports.py` with TimescaleDB `time_bucket()` + `last(value, ts)`
  for cumulative meter readings.
- `TODO(future)`: refresh policies for `telemetry_5m`, retention,
  compression. Redis-backed WS hub for multi-process scaling.

## Open questions for the architect

- Audit column names diverge from the contract (DB:
  `timestamp`/`user_id`/`entity_type`/`entity_id`/`details_json`; contract:
  `ts`/`actor_id`/`target_type`/`target_id`/`metadata`). The schema mapper
  in `schemas.AuditEntryOut.from_row` translates between them so the wire
  shape matches the contract. Confirm this is the desired resolution or
  open a `docs/CONTRACT_CHANGES.md` entry.
- `Alarm.opened_at` (frozen docs) vs `Alarm.timestamp` (data-track prompt)
  - I kept `opened_at` and surface that name on the wire.
