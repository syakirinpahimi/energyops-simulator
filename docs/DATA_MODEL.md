# Data Model

PostgreSQL 15 with the TimescaleDB extension. All tables live in the `public` schema for MVP.

> Convention: every table has `id UUID PRIMARY KEY DEFAULT gen_random_uuid()`, `created_at TIMESTAMPTZ NOT NULL DEFAULT now()`, and (where relevant) `updated_at TIMESTAMPTZ NOT NULL DEFAULT now()` with a trigger.

## Entity-relationship diagram

```
companies ‚îÄ‚îê
           ‚îú‚îÄ< sites ‚îÄ< areas ‚îÄ< assets ‚îÄ< sensors ‚îÄ< telemetry (hypertable)
           ‚îî‚îÄ< users                              ‚îî‚îÄ< alarms
                                                  ‚îî‚îÄ< asset_status_history

audit_log     (references users)
reports       (references users)
```

## Extensions

```sql
CREATE EXTENSION IF NOT EXISTS "pgcrypto";   -- gen_random_uuid()
CREATE EXTENSION IF NOT EXISTS "timescaledb";
```

## Enum types

```sql
CREATE TYPE user_role        AS ENUM ('operator','engineer','manager','admin');
CREATE TYPE asset_status     AS ENUM ('online','offline','fault','maintenance');
CREATE TYPE alarm_state      AS ENUM ('OPEN','ACK','RESOLVED');
CREATE TYPE alarm_severity   AS ENUM ('info','warning','critical');
CREATE TYPE telemetry_quality AS ENUM ('good','uncertain','bad');
CREATE TYPE report_status    AS ENUM ('queued','running','ready','failed');
CREATE TYPE report_format    AS ENUM ('csv','pdf');
```

## Hierarchy tables

```sql
CREATE TABLE companies (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  slug        TEXT NOT NULL UNIQUE,
  name        TEXT NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE TABLE sites (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id  UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
  slug        TEXT NOT NULL,
  name        TEXT NOT NULL,
  timezone    TEXT NOT NULL DEFAULT 'Asia/Kuala_Lumpur',
  location    JSONB,                       -- { lat, lon, address }
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (company_id, slug)
);

CREATE TABLE areas (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  site_id     UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
  slug        TEXT NOT NULL,
  name        TEXT NOT NULL,
  created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (site_id, slug)
);

CREATE TABLE assets (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  area_id         UUID NOT NULL REFERENCES areas(id) ON DELETE CASCADE,
  slug            TEXT NOT NULL,
  name            TEXT NOT NULL,
  asset_type      TEXT NOT NULL,           -- 'boiler','inverter','chiller','ups','meter',...
  status          asset_status NOT NULL DEFAULT 'offline',
  rated_power_kw  NUMERIC(10,2),
  metadata        JSONB NOT NULL DEFAULT '{}',
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (area_id, slug)
);
CREATE INDEX idx_assets_area    ON assets(area_id);
CREATE INDEX idx_assets_status  ON assets(status);
CREATE INDEX idx_assets_type    ON assets(asset_type);

CREATE TABLE sensors (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  asset_id     UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
  metric       TEXT NOT NULL,              -- 'power_kw','temperature_c','voltage_v',...
  unit         TEXT NOT NULL,              -- 'kW','¬∞C','V'
  description  TEXT,
  min_value    NUMERIC,
  max_value    NUMERIC,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (asset_id, metric)
);
CREATE INDEX idx_sensors_asset ON sensors(asset_id);
```

## Users

```sql
CREATE TABLE users (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  company_id      UUID NOT NULL REFERENCES companies(id) ON DELETE RESTRICT,
  email           CITEXT NOT NULL UNIQUE,    -- requires `citext` extension; or use TEXT + lower() index
  name            TEXT NOT NULL,
  password_hash   TEXT NOT NULL,             -- bcrypt or argon2
  role            user_role NOT NULL,
  is_active       BOOLEAN NOT NULL DEFAULT TRUE,
  last_login_at   TIMESTAMPTZ,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_users_company ON users(company_id);
```

> If `citext` is unavailable, use `email TEXT NOT NULL` with a unique index on `lower(email)`.

## Telemetry (TimescaleDB hypertable)

The hot path. All sensor readings flow into this table.

```sql
CREATE TABLE telemetry (
  ts         TIMESTAMPTZ NOT NULL,
  asset_id   UUID NOT NULL,
  sensor_id  UUID NOT NULL,
  metric     TEXT NOT NULL,
  value      DOUBLE PRECISION NOT NULL,
  quality    telemetry_quality NOT NULL DEFAULT 'good',
  PRIMARY KEY (sensor_id, ts)
);

-- Convert to hypertable, 1 day chunks (tune later).
SELECT create_hypertable('telemetry', 'ts', chunk_time_interval => INTERVAL '1 day');

CREATE INDEX idx_telemetry_asset_ts  ON telemetry (asset_id, ts DESC);
CREATE INDEX idx_telemetry_metric_ts ON telemetry (metric, ts DESC);
```

### Continuous aggregates

For fast historical chart queries:

```sql
CREATE MATERIALIZED VIEW telemetry_5m
WITH (timescaledb.continuous) AS
SELECT
  time_bucket('5 minutes', ts) AS bucket,
  asset_id, sensor_id, metric,
  AVG(value) AS avg_value,
  MIN(value) AS min_value,
  MAX(value) AS max_value,
  LAST(value, ts) AS last_value
FROM telemetry
GROUP BY bucket, asset_id, sensor_id, metric;

SELECT add_continuous_aggregate_policy('telemetry_5m',
  start_offset => INTERVAL '7 days',
  end_offset   => INTERVAL '5 minutes',
  schedule_interval => INTERVAL '5 minutes');
```

A second view `telemetry_1h` with the same shape and `1 hour` bucket. The backend chooses which view to query based on the requested `bucket` size.

### Retention policy

```sql
-- Drop raw telemetry older than 90 days; keep aggregates for 2 years.
SELECT add_retention_policy('telemetry',    INTERVAL '90 days');
SELECT add_retention_policy('telemetry_5m', INTERVAL '730 days');
```

### Compression

```sql
ALTER TABLE telemetry SET (
  timescaledb.compress,
  timescaledb.compress_segmentby = 'sensor_id',
  timescaledb.compress_orderby   = 'ts DESC'
);
SELECT add_compression_policy('telemetry', INTERVAL '7 days');
```

## Alarms

```sql
CREATE TABLE alarms (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  asset_id     UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
  sensor_id    UUID REFERENCES sensors(id) ON DELETE SET NULL,
  code         TEXT NOT NULL,                  -- e.g. 'TEMP_HIGH','POWER_LOST'
  severity     alarm_severity NOT NULL,
  message      TEXT NOT NULL,
  state        alarm_state NOT NULL DEFAULT 'OPEN',
  opened_at    TIMESTAMPTZ NOT NULL DEFAULT now(),
  acked_at     TIMESTAMPTZ,
  acked_by     UUID REFERENCES users(id) ON DELETE SET NULL,
  ack_note     TEXT,
  resolved_at  TIMESTAMPTZ,
  resolved_by  UUID REFERENCES users(id) ON DELETE SET NULL,
  resolve_note TEXT,
  created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_alarms_state_opened ON alarms(state, opened_at DESC);
CREATE INDEX idx_alarms_asset_state  ON alarms(asset_id, state);
CREATE INDEX idx_alarms_severity     ON alarms(severity);

-- Only one OPEN alarm per (asset, code) at a time.
CREATE UNIQUE INDEX uq_alarms_open_per_asset_code
  ON alarms(asset_id, code) WHERE state = 'OPEN';
```

## Asset status history

Snapshot of every status transition. Used for the timeline view and uptime calculations.

```sql
CREATE TABLE asset_status_history (
  id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  asset_id    UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
  status      asset_status NOT NULL,
  reason      TEXT,
  ts          TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX idx_status_hist_asset_ts ON asset_status_history(asset_id, ts DESC);
```

## Audit log

```sql
CREATE TABLE audit_log (
  id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  ts           TIMESTAMPTZ NOT NULL DEFAULT now(),
  actor_id     UUID REFERENCES users(id) ON DELETE SET NULL,
  actor_email  TEXT NOT NULL,                 -- denormalised so it survives user deletion
  action       TEXT NOT NULL,                 -- 'alarm.ack','asset.update',...
  target_type  TEXT,                          -- 'alarm','asset','user','report',...
  target_id    UUID,
  metadata     JSONB NOT NULL DEFAULT '{}'
);
CREATE INDEX idx_audit_ts          ON audit_log(ts DESC);
CREATE INDEX idx_audit_actor_ts    ON audit_log(actor_id, ts DESC);
CREATE INDEX idx_audit_action      ON audit_log(action);
CREATE INDEX idx_audit_target      ON audit_log(target_type, target_id);
```

The audit log is **append-only**. Do not expose update/delete handlers.

## Reports

```sql
CREATE TABLE reports (
  id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  kind            TEXT NOT NULL,              -- 'energy','alarms','uptime'
  format          report_format NOT NULL,
  status          report_status NOT NULL DEFAULT 'queued',
  params          JSONB NOT NULL,             -- { site_id, from, to, ... }
  file_path       TEXT,                       -- relative to /app/reports
  file_size_bytes BIGINT,
  error           TEXT,
  created_by      UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
  created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
  finished_at     TIMESTAMPTZ
);
CREATE INDEX idx_reports_creator_ts ON reports(created_by, created_at DESC);
CREATE INDEX idx_reports_status     ON reports(status);
```

## Seed data shape

The backend seed script (`backend/app/seed.py`, TODO) populates the database with one company, three sites, and a realistic asset mix. Operators can run it via `docker compose exec backend python -m app.seed`.

```yaml
company:
  slug: acme
  name: Acme Industrial Sdn Bhd

sites:
  - slug: kuantan-plant
    name: Kuantan Plant
    timezone: Asia/Kuala_Lumpur
    location: { lat: 3.8077, lon: 103.3260, address: "Kuantan, Pahang" }
    areas:
      - { slug: boiler-hall,    name: "Boiler Hall" }
      - { slug: substation-a,   name: "Substation A" }
      - { slug: compressor-bay, name: "Compressor Bay" }

  - slug: johor-solar
    name: Johor Solar Farm
    timezone: Asia/Kuala_Lumpur
    location: { lat: 1.4927, lon: 103.7414, address: "Iskandar Puteri, Johor" }
    areas:
      - { slug: inverter-row-a, name: "Inverter Row A" }
      - { slug: inverter-row-b, name: "Inverter Row B" }
      - { slug: substation,     name: "Substation" }

  - slug: kl-data-centre
    name: KL Data Centre
    timezone: Asia/Kuala_Lumpur
    location: { lat: 3.1390, lon: 101.6869, address: "Kuala Lumpur" }
    areas:
      - { slug: cooling,    name: "Cooling" }
      - { slug: ups-room,   name: "UPS Room" }
      - { slug: server-hall-1, name: "Server Hall 1" }
```

### Asset mix per site

| Site            | Asset types and counts                                      |
|-----------------|-------------------------------------------------------------|
| Kuantan Plant   | 3◊ boiler, 2◊ compressor, 1◊ main meter                      |
| Johor Solar     | 12◊ inverter (split across 2 rows), 1◊ substation meter      |
| KL Data Centre  | 2◊ chiller, 4◊ UPS, 2◊ PDU, 1◊ main meter                    |

### Sensor template per asset type

| Asset type | Sensors                                                  |
|------------|----------------------------------------------------------|
| boiler     | `power_kw`, `temperature_c`, `pressure_bar`, `fuel_flow_lpm` |
| compressor | `power_kw`, `pressure_bar`, `vibration_mm_s`             |
| inverter   | `power_kw`, `dc_voltage_v`, `ac_voltage_v`, `temperature_c` |
| chiller    | `power_kw`, `supply_temp_c`, `return_temp_c`, `flow_lps` |
| ups        | `load_kw`, `battery_pct`, `input_voltage_v`              |
| pdu        | `power_kw`, `current_a`                                  |
| meter      | `power_kw`, `energy_kwh`, `voltage_v`, `current_a`       |

### Backfill

The seed script also writes ~7 days of synthetic historical telemetry into the hypertable so that charts have something to display before the simulator runs. Generation rules:

- Solar inverters follow a daylight curve (zero at night, peak ~14:00 local).
- Boilers/chillers follow a slight workday pattern.
- Add ±5% gaussian noise.
- Inject 3ñ5 historical alarms per site, mixed severities, half resolved.

### Demo users

Created from the `SEED_*` env vars. One per role, all under the seeded company.

## Migrations

Use Alembic in the backend. The first migration `0001_initial.sql` creates everything in this document. Subsequent changes go in numbered Alembic revisions; do not edit `0001_initial.sql` after the first release.

## Sample queries

```sql
-- Latest value per sensor for an asset
SELECT DISTINCT ON (sensor_id)
       sensor_id, metric, value, ts
FROM   telemetry
WHERE  asset_id = $1
ORDER  BY sensor_id, ts DESC;

-- 5-minute average power for the last hour
SELECT bucket, avg_value
FROM   telemetry_5m
WHERE  asset_id = $1
  AND  metric   = 'power_kw'
  AND  bucket  >= now() - INTERVAL '1 hour'
ORDER  BY bucket;

-- Open alarm count per site
SELECT s.id AS site_id, s.name, COUNT(*) AS open_alarms
FROM   alarms al
JOIN   assets a ON a.id = al.asset_id
JOIN   areas  ar ON ar.id = a.area_id
JOIN   sites  s  ON s.id = ar.site_id
WHERE  al.state = 'OPEN'
GROUP  BY s.id, s.name;
```
