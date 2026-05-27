# Architecture

System overview for the Industrial EnergyOps Dashboard. Read this first.

## High-level diagram

```
                ┌─────────────────────────────────────────────────────────┐
                │                       Browsers                          │
                │              (operators, engineers, etc.)               │
                └──────────────┬──────────────────────────┬───────────────┘
                               │ HTTPS REST                │ WebSocket
                               │ /api/v1/*                 │ /ws/telemetry
                               ▼                           ▼
                ┌─────────────────────────────────────────────────────────┐
                │                  Next.js Frontend                       │
                │       (App Router, TypeScript, Tailwind, Recharts)      │
                └──────────────┬──────────────────────────────────────────┘
                               │ HTTP + WS
                               ▼
                ┌─────────────────────────────────────────────────────────┐
                │                  FastAPI Backend                        │
                │   ┌──────────┐ ┌──────────┐ ┌──────────┐ ┌──────────┐  │
                │   │ Auth/JWT │ │ REST API │ │   WS hub │ │ Reports  │  │
                │   └──────────┘ └──────────┘ └────┬─────┘ └──────────┘  │
                │                                  │                      │
                │                       ┌──────────┴────────┐             │
                │                       │ MQTT subscriber   │             │
                │                       │ (background task) │             │
                │                       └──────────┬────────┘             │
                └──────────┬───────────────────────┼─────────────────────-┘
                           │ SQL                   │ MQTT subscribe
                           ▼                       ▼
        ┌──────────────────────────────┐   ┌──────────────────────────┐
        │   PostgreSQL + TimescaleDB   │   │   Mosquitto MQTT Broker  │
        │   (relational + hypertables) │   │   (topics: see API doc)  │
        └──────────────────────────────┘   └────────────▲─────────────┘
                                                        │ MQTT publish
                                            ┌───────────┴───────────┐
                                            │   Python Simulator    │
                                            │ (paho-mqtt publisher) │
                                            └───────────────────────┘
```

## Services

| Service     | Responsibility                                                                 | Port  |
|-------------|--------------------------------------------------------------------------------|-------|
| `frontend`  | Next.js UI: dashboards, asset views, alarms, reports                           | 3000  |
| `backend`   | FastAPI: REST API, JWT auth, WS broadcast, MQTT subscriber, report generation  | 8000  |
| `postgres`  | PostgreSQL 15 + TimescaleDB extension, all persistent state                    | 5432  |
| `mosquitto` | MQTT broker, telemetry transport between simulator and backend                 | 1883  |
| `simulator` | Generates synthetic telemetry for seeded assets and publishes to MQTT          | n/a   |

All services run via `docker compose up`. Each has its own folder and `Dockerfile`.

## Data flow

### Live telemetry (write path)

1. `simulator` reads the seeded asset list (via REST `GET /api/v1/assets` or local config) and on each tick publishes a telemetry payload per sensor to MQTT.
2. `mosquitto` routes the message.
3. `backend` MQTT subscriber receives the message, validates payload schema, writes to the `telemetry` hypertable, and updates derived asset status if needed.
4. `backend` rebroadcasts the telemetry payload to subscribed WebSocket clients on `/ws/telemetry`.
5. `frontend` updates Recharts streams and asset tiles in place.

### Alarm flow

1. The simulator (or a backend rule, post-MVP) emits an alarm event on the alarm topic.
2. `backend` persists it to the `alarms` table with `state = 'OPEN'`.
3. `frontend` shows it in the alarm panel for `operator+` roles.
4. An operator acknowledges via `POST /api/v1/alarms/{id}/ack`. The backend updates `state = 'ACK'`, writes an `audit_log` entry, and broadcasts the updated alarm.
5. An engineer/manager can resolve via `POST /api/v1/alarms/{id}/resolve`.

### Historical query (read path)

1. Frontend chart calls `GET /api/v1/telemetry?asset_id=...&metric=power_kw&from=...&to=...&bucket=5m`.
2. Backend uses Timescale `time_bucket()` to aggregate.
3. Response is JSON array `[{ ts, value }]`. Frontend feeds it into Recharts.

### Reports

1. User requests `GET /api/v1/reports/energy?site_id=...&from=...&to=...&format=pdf`.
2. Backend queries Timescale, builds the artefact (CSV via stdlib, PDF via `reportlab`), writes to `/app/reports/`, and streams it back.
3. Files persist in the `reports/` volume so they can be re-downloaded by id.

## Plant hierarchy

```
company
  └── site            (e.g. "Kuantan Plant")
        └── area      (e.g. "Boiler Hall", "Substation A")
              └── asset       (e.g. "Boiler #2", "Inverter String 4")
                    └── sensor (e.g. "power_kw", "temperature_c")
```

Each level has a UUID primary key and a parent FK. See `DATA_MODEL.md` for full schema.

## Authentication and authorisation

- Simple JWT bearer auth. No refresh tokens for MVP.
- `POST /api/v1/auth/login` returns `{ access_token, token_type, user }`.
- `Authorization: Bearer <token>` on all protected endpoints.
- The `role` claim is one of `operator | engineer | manager | admin`.
- Role permissions are enforced via a FastAPI dependency. See `API_CONTRACT.md` § Role permissions.

## Concurrency and scale (MVP scope)

This is a single-node demo. Assumptions:

- One backend process. WS clients are tracked in-memory.
- One MQTT broker, no clustering.
- Postgres is the source of truth; everything else is derived.
- Targeted load: ~50 assets, ~5 sensors each, 5s tick → ~50 msg/s. Comfortably within a single FastAPI worker.

If you need to scale beyond this, swap the in-memory WS hub for Redis pub/sub. Out of scope for MVP — leave a TODO in the WS hub module.

## Configuration

All configuration is via environment variables. See `.env.example` for the full list. The backend uses `pydantic-settings` to load and validate at startup; a missing required var should crash the process loudly rather than fall back silently.

## Logging and observability

- Python services log JSON to stdout at `LOG_LEVEL` (default `INFO`).
- FastAPI access logs come from Uvicorn.
- For MVP, no metrics exporter. Leave a `TODO(observability)` for a `/metrics` Prometheus endpoint.

## Out of scope for MVP

- Multi-tenancy isolation beyond the `company` row
- Refresh tokens / password reset flows
- Forecasting or ML
- Mobile app
- High availability / clustering
- TLS termination (assume reverse proxy handles it in production)

These should each have a brief `TODO(future)` in the relevant module so they aren't lost.

## Known limitations and production roadmap

The MVP is scoped to a single-node demo. The items below are the
deliberate architectural cut lines between the demo and a production
deployment, captured here so the roadmap is explicit.

### Read-path: continuous aggregates for reports

Reports query the raw `telemetry` hypertable today. At MVP cardinality
this is fine, but report latency grows linearly with the date range. The
roadmap routes long-window queries through the existing
`telemetry_5m` continuous aggregate (and a planned `telemetry_1h`
companion), with the report layer selecting the aggregate table based
on the requested range. Raw telemetry is reserved for short windows
and drill-downs.

### Energy roll-up: counter rollover handling

Energy consumption per asset is currently `MAX(value) - MIN(value)`
over the window, which is correct for monotonic meters within a chunk
but mishandles meter resets and counter rollover. The production path
uses a `LAG`-based delta sum (`SUM(GREATEST(value - LAG(value), 0))`)
so resets and replacements do not inflate consumption.

### Reporting: site-local timezones

Report windows are evaluated in UTC. The data model already carries
`sites.timezone` (default `Asia/Kuala_Lumpur`); the roadmap threads it
through the report layer so business-day, business-week, and
business-month reports align with each site's local calendar instead
of the server's clock.

### Reporting: alarm window semantics

Alarm reports filter on `opened_at` falling inside the selected
window. The roadmap adds an "active during window" mode that also
includes alarms opened before the window but resolved (or still open)
during it - the semantic operations teams expect for shift-handover
reports.

### Reporting: large export delivery

CSV export is capped at 100,000 rows with `X-Report-Truncated` and
`X-Report-Row-Limit` response headers so clients can detect
truncation deterministically. The roadmap moves large exports to an
async report job queue with object-storage delivery, removing the cap
for managers who need full multi-month dumps without holding the
request thread open.

### Ingest and fan-out

- Wire `services.mqtt_consumer.MqttConsumer` into the FastAPI lifespan
  with `ws_hub.broadcast` as the fan-out callback so live ingestion
  starts with the process.
- Move the in-memory WS hub onto Redis pub/sub for multi-worker
  scale-out and honour per-asset / per-site subscription filters.

### Platform

- Refresh tokens, password reset, and httpOnly cookie delivery via a
  Next.js Route Handler.
- `/metrics` Prometheus endpoint plus a Grafana side-car
  (`TODO(observability)`).
- Postgres replicas, broker clustering, and TLS termination at the
  reverse proxy for HA deployments.
