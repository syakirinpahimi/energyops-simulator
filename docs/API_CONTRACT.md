# API Contract

REST + WebSocket + MQTT contracts for the Industrial EnergyOps Dashboard. This is the source of truth for inter-service communication.

> Versioning: all REST endpoints are under `/api/v1`. Bump to `/api/v2` for any breaking change.

## Conventions

- **Format**: JSON only. `Content-Type: application/json`.
- **Identifiers**: UUID v4 strings.
- **Timestamps**: ISO 8601 UTC with `Z` suffix, e.g. `2026-05-27T10:15:30Z`.
- **Numbers**: floats are SI units (W, Wh, °C, etc.). Display unit conversion happens in the frontend.
- **Pagination**: cursor-style. `?limit=50&cursor=<opaque>`. Response includes `next_cursor` (nullable).
- **Errors**: see *Error envelope* below. Always returned with the appropriate HTTP status code.

## Error envelope

```json
{
  "error": {
    "code": "ALARM_NOT_FOUND",
    "message": "Alarm 4f8c… does not exist",
    "details": { "alarm_id": "4f8c…" }
  }
}
```

| HTTP | When                                              |
|------|---------------------------------------------------|
| 400  | Validation failed                                  |
| 401  | Missing or invalid JWT                            |
| 403  | Authenticated but role lacks permission           |
| 404  | Resource not found                                |
| 409  | State conflict (e.g. acknowledging a closed alarm) |
| 422  | Schema validation error from FastAPI/Pydantic     |
| 500  | Unhandled error                                   |

## Authentication

All endpoints except `/api/v1/auth/login` and `/api/v1/health` require:

```
Authorization: Bearer <jwt>
```

JWT payload:

```json
{
  "sub": "<user_uuid>",
  "email": "operator@energyops.local",
  "role": "operator",
  "company_id": "<company_uuid>",
  "exp": 1730000000,
  "iat": 1729996400
}
```

## Role permissions

| Action                          | operator | engineer | manager | admin |
|---------------------------------|:--------:|:--------:|:-------:|:-----:|
| View dashboards / telemetry     | ✓        | ✓        | ✓       | ✓     |
| Acknowledge alarms              | ✓        | ✓        | ✓       | ✓     |
| Resolve / close alarms          |          | ✓        | ✓       | ✓     |
| Edit asset metadata             |          | ✓        | ✓       | ✓     |
| Generate reports                |          |          | ✓       | ✓     |
| Manage users / roles            |          |          |         | ✓     |
| View audit log                  |          | ✓        | ✓       | ✓     |
| Manage hierarchy (sites/areas)  |          |          | ✓       | ✓     |

Enforcement lives in a single FastAPI dependency (`require_role(*roles)`). Do not scatter role checks across handlers.

## REST endpoints

### Health

```
GET /api/v1/health  -> 200 { "status": "ok", "version": "0.1.0" }
```

### Auth

```
POST /api/v1/auth/login
  body: { "email": "...", "password": "..." }
  200:  { "access_token": "...", "token_type": "bearer", "user": <User> }
  401:  invalid credentials

GET  /api/v1/auth/me
  200:  <User>
```

`<User>`:

```json
{
  "id": "uuid",
  "email": "operator@energyops.local",
  "name": "Aisyah",
  "role": "operator",
  "company_id": "uuid",
  "created_at": "2026-05-01T08:00:00Z"
}
```

### Hierarchy

```
GET /api/v1/companies                           -> [<Company>]
GET /api/v1/sites?company_id=<uuid>             -> [<Site>]
GET /api/v1/areas?site_id=<uuid>                -> [<Area>]
GET /api/v1/assets?area_id=<uuid>               -> [<Asset>]
GET /api/v1/assets/{asset_id}                   -> <Asset>
GET /api/v1/assets/{asset_id}/sensors           -> [<Sensor>]

# Manager+ (write)
POST   /api/v1/sites                            -> <Site>
POST   /api/v1/areas                            -> <Area>
POST   /api/v1/assets                           -> <Asset>
PATCH  /api/v1/assets/{asset_id}                -> <Asset>
DELETE /api/v1/assets/{asset_id}                -> 204
```

`<Asset>`:

```json
{
  "id": "uuid",
  "area_id": "uuid",
  "name": "Boiler #2",
  "asset_type": "boiler",
  "status": "online",
  "rated_power_kw": 350.0,
  "metadata": { "model": "ACME-B200", "installed": "2022-03-15" },
  "created_at": "2026-05-01T08:00:00Z"
}
```

`status` ? `online | offline | fault | maintenance`.

### Telemetry (history)

```
GET /api/v1/telemetry
  query:
    asset_id   uuid       required
    metric     string     required (e.g. "power_kw", "temperature_c")
    from       iso8601    required
    to         iso8601    required
    bucket     string     optional, default "1m". One of: 10s, 1m, 5m, 15m, 1h, 1d
    agg        string     optional, default "avg". One of: avg, min, max, sum, last
  200: {
    "asset_id": "uuid",
    "metric": "power_kw",
    "bucket": "1m",
    "agg": "avg",
    "points": [ { "ts": "2026-05-27T10:00:00Z", "value": 312.4 }, ... ]
  }
```

### Asset status snapshot

```
GET /api/v1/assets/{asset_id}/snapshot
  200: {
    "asset_id": "uuid",
    "status": "online",
    "last_seen": "2026-05-27T10:15:25Z",
    "metrics": {
      "power_kw":       { "value": 312.4, "ts": "2026-05-27T10:15:25Z" },
      "temperature_c":  { "value":  72.1, "ts": "2026-05-27T10:15:25Z" }
    },
    "open_alarms": 1
  }
```

### Alarms

```
GET  /api/v1/alarms
  query: state=OPEN|ACK|RESOLVED  site_id?  asset_id?  severity?  limit  cursor
  200:  { "items": [<Alarm>], "next_cursor": null }

GET  /api/v1/alarms/{id}                          -> <Alarm>

POST /api/v1/alarms/{id}/ack                      # operator+
  body: { "note": "investigating" }
  200:  <Alarm>   (state="ACK")
  409:  alarm not in OPEN state

POST /api/v1/alarms/{id}/resolve                  # engineer+
  body: { "note": "replaced sensor" }
  200:  <Alarm>   (state="RESOLVED")
```

`<Alarm>`:

```json
{
  "id": "uuid",
  "asset_id": "uuid",
  "sensor_id": "uuid",
  "code": "TEMP_HIGH",
  "severity": "critical",
  "message": "Temperature exceeded 95�C",
  "state": "OPEN",
  "opened_at": "2026-05-27T10:14:01Z",
  "acked_at": null,
  "acked_by": null,
  "resolved_at": null,
  "resolved_by": null
}
```

`severity` ? `info | warning | critical`. `state` ? `OPEN | ACK | RESOLVED`.

### Reports

```
POST /api/v1/reports/energy                       # manager+
  body: {
    "site_id": "uuid",
    "from":    "2026-05-01T00:00:00Z",
    "to":      "2026-05-27T00:00:00Z",
    "format":  "pdf"   // or "csv"
  }
  202: { "report_id": "uuid", "status": "queued" }

GET /api/v1/reports/{report_id}                   -> <Report>
GET /api/v1/reports/{report_id}/download          -> binary stream
```

`<Report>`:

```json
{
  "id": "uuid",
  "kind": "energy",
  "format": "pdf",
  "status": "ready",
  "params": { "site_id": "...", "from": "...", "to": "..." },
  "file_size_bytes": 184320,
  "created_by": "uuid",
  "created_at": "2026-05-27T10:00:00Z"
}
```

### Audit log

```
GET /api/v1/audit                                 # engineer+
  query: actor_id?  action?  from?  to?  limit  cursor
  200:  { "items": [<AuditEntry>], "next_cursor": null }
```

`<AuditEntry>`:

```json
{
  "id": "uuid",
  "ts": "2026-05-27T10:14:30Z",
  "actor_id": "uuid",
  "actor_email": "operator@energyops.local",
  "action": "alarm.ack",
  "target_type": "alarm",
  "target_id": "uuid",
  "metadata": { "note": "investigating" }
}
```

Recorded actions (MVP):

- `auth.login`, `auth.login_failed`
- `alarm.ack`, `alarm.resolve`
- `asset.create`, `asset.update`, `asset.delete`
- `report.create`, `report.download`
- `user.create`, `user.update`, `user.delete`

## WebSocket: live telemetry

The backend exposes a single WebSocket endpoint for live updates. Token is passed as a query param (browsers can't send custom headers on WS).

```
WS  /ws/telemetry?token=<jwt>
```

### Lifecycle

1. Client connects with a valid JWT. Backend validates and accepts. Invalid ? close with code `4401`.
2. Client sends a `subscribe` message listing assets it cares about.
3. Backend pushes `telemetry`, `status`, and `alarm` events as they happen.
4. Client may send `unsubscribe` or change subscriptions at any time.
5. Backend sends a `ping` every 30s; client must respond with `pong` or be disconnected.

### Client ? server messages

```json
{ "type": "subscribe",   "asset_ids": ["uuid1", "uuid2"] }
{ "type": "unsubscribe", "asset_ids": ["uuid1"] }
{ "type": "subscribe_site", "site_id": "uuid" }
{ "type": "pong" }
```

### Server ? client messages

```json
// Telemetry sample (one message per sensor reading)
{
  "type": "telemetry",
  "asset_id": "uuid",
  "sensor_id": "uuid",
  "metric": "power_kw",
  "value": 312.4,
  "ts": "2026-05-27T10:15:25Z"
}

// Asset status change
{
  "type": "status",
  "asset_id": "uuid",
  "status": "fault",
  "ts": "2026-05-27T10:15:30Z"
}

// New or updated alarm
{
  "type": "alarm",
  "alarm": <Alarm>
}

// Liveness
{ "type": "ping", "ts": "2026-05-27T10:15:00Z" }
```

Close codes:

| Code | Reason                        |
|------|-------------------------------|
| 1000 | Normal closure                |
| 4401 | Invalid or expired token      |
| 4403 | Role lacks permission         |
| 4408 | Heartbeat timeout             |

## MQTT topic conventions

The simulator publishes; the backend subscribes. Wildcards (`+`, `#`) follow MQTT 3.1.1. Decision recorded in [`docs/adr/0001-mqtt-topic-contract.md`](adr/0001-mqtt-topic-contract.md).

### Naming convention

```
industrial/<site_slug>/<area_slug>/<asset_slug>/<sensor_slug>
```

- Five segments. No company segment; the company is single-tenant for MVP and travels in the JSON payload.
- `<*_slug>`: lowercase, hyphenated, no spaces, stable across restarts.
- `<sensor_slug>` is the metric channel for telemetry (e.g. `power_kw`, `vibration_mm_s`). Reserved per-asset channels reuse the same slot with an underscore prefix:
  - `_status`    -- asset status transitions (`retain=true`)
  - `_heartbeat` -- liveness ping (`retain=false`)

This keeps a single five-segment wildcard subscription matching every published topic.

### Concrete examples

```
industrial/kuantan-plant/utilities/pump-p-101/vibration_mm_s
industrial/kuantan-plant/compressor-bay/air-compressor-c-201/temperature_c
industrial/kl-data-centre/cooling/hvac-chiller-ch-1/power_kw
industrial/johor-solar/inverter-row-a/solar-inverter-inv-01/energy_kwh
industrial/kuantan-plant/substation/main-grid-meter-gm-01/voltage_v
industrial/kuantan-plant/utilities/pump-p-101/_status
industrial/kuantan-plant/utilities/pump-p-101/_heartbeat
```

### Backend subscription

The backend subscribes to a single filter:

```
industrial/+/+/+/+
```

QoS 1 for all channels. `retain=false` for telemetry and heartbeat; `retain=true` for the latest `_status` so new subscribers see current state.

### Payload schemas

`telemetry` (one reading per message, published on `<sensor_slug>` topics):

```json
{
  "timestamp": "2026-05-27T10:15:25Z",
  "company": "Demo Industrial Holdings",
  "site": "Kuantan Plant",
  "area": "Utilities",
  "asset": "Pump P-101",
  "sensor": "vibration_mm_s",
  "metric": "vibration_mm_s",
  "value": 8.4,
  "unit": "mm/s",
  "quality": "good",
  "anomaly": "vibration_spike"
}
```

`quality` -> `good | uncertain | bad`. Default `good`. `anomaly` is nullable; the backend treats `null` as normal operation.

`_status` (published on `.../_status`, `retain=true`):

```json
{
  "timestamp": "2026-05-27T10:15:25Z",
  "site": "Kuantan Plant",
  "asset": "Pump P-101",
  "status": "fault",
  "reason": "vibration_spike"
}
```

`_heartbeat` (published on `.../_heartbeat`, `retain=false`):

```json
{
  "timestamp": "2026-05-27T10:15:00Z",
  "asset": "Pump P-101"
}
```

> Alarm events do not flow on a dedicated MQTT topic in this MVP. The backend opens alarms from the threshold engine when telemetry breaches a rule, persists them, and re-broadcasts the resulting `alarm` event over WebSocket (see *WebSocket: live telemetry*).

### Validation rules

The backend MQTT subscriber must:

1. Reject topics that do not have exactly five segments.
2. Reject samples whose `timestamp` is more than 5 minutes in the future.
3. Drop messages whose `quality == "bad"` from telemetry inserts but log them.
4. Be idempotent on `(asset_id, sensor_id, ts)` -- duplicates are discarded.
5. Skip messages whose `(site_slug, area_slug, asset_slug)` chain is unknown (no row in the hierarchy tables); log at `DEBUG`.

### Error / dead-letter

Malformed messages are logged with the raw topic + payload at `WARNING`. There is no dead-letter topic for MVP -- a `TODO(reliability)` lives in the subscriber.

## Request examples

```bash
# Login
curl -X POST http://localhost:8000/api/v1/auth/login \
  -H 'Content-Type: application/json' \
  -d '{"email":"operator@energyops.local","password":"Operator#12345"}'

# Get assets in an area
curl http://localhost:8000/api/v1/assets?area_id=$AREA_ID \
  -H "Authorization: Bearer $TOKEN"

# History query
curl "http://localhost:8000/api/v1/telemetry?asset_id=$AID&metric=power_kw&from=2026-05-27T00:00:00Z&to=2026-05-27T12:00:00Z&bucket=5m" \
  -H "Authorization: Bearer $TOKEN"

# Acknowledge an alarm
curl -X POST http://localhost:8000/api/v1/alarms/$ALARM_ID/ack \
  -H "Authorization: Bearer $TOKEN" \
  -H 'Content-Type: application/json' \
  -d '{"note":"investigating"}'
```
