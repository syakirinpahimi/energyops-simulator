"""initial schema with TimescaleDB

Revision ID: 0001_initial
Revises:
Create Date: 2026-05-27

Creates extensions, enums, tables, indexes, the telemetry hypertable,
and one continuous aggregate (telemetry_5m). Kept as a single revision
because everything in this file is the "v1 baseline".
"""
from __future__ import annotations

from typing import Sequence, Union

from alembic import op


# revision identifiers, used by Alembic.
revision: str = "0001_initial"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # ------------------------------------------------------------------
    # Extensions
    # ------------------------------------------------------------------
    op.execute('CREATE EXTENSION IF NOT EXISTS "pgcrypto";')
    op.execute('CREATE EXTENSION IF NOT EXISTS "timescaledb";')

    # ------------------------------------------------------------------
    # Enum types
    # ------------------------------------------------------------------
    op.execute(
        "CREATE TYPE user_role AS ENUM "
        "('operator','engineer','manager','admin');"
    )
    op.execute(
        "CREATE TYPE asset_status AS ENUM "
        "('online','offline','fault','maintenance');"
    )
    op.execute("CREATE TYPE alarm_state AS ENUM ('OPEN','ACK','RESOLVED');")
    op.execute(
        "CREATE TYPE alarm_severity AS ENUM ('info','warning','critical');"
    )
    op.execute(
        "CREATE TYPE telemetry_quality AS ENUM ('good','uncertain','bad');"
    )
    op.execute(
        "CREATE TYPE report_status AS ENUM "
        "('queued','running','ready','failed');"
    )
    op.execute("CREATE TYPE report_format AS ENUM ('csv','pdf');")

    # ------------------------------------------------------------------
    # Hierarchy tables
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE companies (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            slug        TEXT NOT NULL UNIQUE,
            name        TEXT NOT NULL,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        """
    )

    op.execute(
        """
        CREATE TABLE sites (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id  UUID NOT NULL REFERENCES companies(id) ON DELETE CASCADE,
            slug        TEXT NOT NULL,
            name        TEXT NOT NULL,
            timezone    TEXT NOT NULL DEFAULT 'Asia/Kuala_Lumpur',
            location    JSONB,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_sites_company_slug UNIQUE (company_id, slug)
        );
        """
    )

    op.execute(
        """
        CREATE TABLE areas (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            site_id     UUID NOT NULL REFERENCES sites(id) ON DELETE CASCADE,
            slug        TEXT NOT NULL,
            name        TEXT NOT NULL,
            created_at  TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_areas_site_slug UNIQUE (site_id, slug)
        );
        """
    )

    op.execute(
        """
        CREATE TABLE assets (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            area_id         UUID NOT NULL REFERENCES areas(id) ON DELETE CASCADE,
            slug            TEXT NOT NULL,
            name            TEXT NOT NULL,
            asset_type      TEXT NOT NULL,
            status          asset_status NOT NULL DEFAULT 'offline',
            rated_power_kw  NUMERIC(10,2),
            metadata        JSONB NOT NULL DEFAULT '{}'::jsonb,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_assets_area_slug UNIQUE (area_id, slug)
        );
        CREATE INDEX idx_assets_area    ON assets(area_id);
        CREATE INDEX idx_assets_status  ON assets(status);
        CREATE INDEX idx_assets_type    ON assets(asset_type);
        """
    )

    op.execute(
        """
        CREATE TABLE sensors (
            id           UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            asset_id     UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
            metric       TEXT NOT NULL,
            unit         TEXT NOT NULL,
            description  TEXT,
            min_value    NUMERIC,
            max_value    NUMERIC,
            created_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_sensors_asset_metric UNIQUE (asset_id, metric)
        );
        CREATE INDEX idx_sensors_asset ON sensors(asset_id);
        """
    )

    # ------------------------------------------------------------------
    # Users
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE users (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            company_id      UUID NOT NULL REFERENCES companies(id) ON DELETE RESTRICT,
            email           TEXT NOT NULL,
            name            TEXT NOT NULL,
            password_hash   TEXT NOT NULL,
            role            user_role NOT NULL,
            is_active       BOOLEAN NOT NULL DEFAULT TRUE,
            last_login_at   TIMESTAMPTZ,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX idx_users_company ON users(company_id);
        CREATE UNIQUE INDEX idx_users_email_lower ON users (lower(email));
        """
    )

    # ------------------------------------------------------------------
    # Telemetry hypertable
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE telemetry (
            ts          TIMESTAMPTZ NOT NULL,
            company_id  UUID NOT NULL,
            site_id     UUID NOT NULL,
            area_id     UUID NOT NULL,
            asset_id    UUID NOT NULL,
            sensor_id   UUID NOT NULL,
            metric      TEXT NOT NULL,
            value       DOUBLE PRECISION NOT NULL,
            unit        TEXT NOT NULL,
            quality     telemetry_quality NOT NULL DEFAULT 'good',
            PRIMARY KEY (sensor_id, ts)
        );
        """
    )
    # Convert to hypertable (1-day chunks). `if_not_exists` keeps reruns safe.
    op.execute(
        "SELECT create_hypertable('telemetry', 'ts', "
        "chunk_time_interval => INTERVAL '1 day', if_not_exists => TRUE);"
    )
    op.execute(
        """
        CREATE INDEX idx_telemetry_asset_ts  ON telemetry (asset_id,  ts DESC);
        CREATE INDEX idx_telemetry_metric_ts ON telemetry (metric,    ts DESC);
        CREATE INDEX idx_telemetry_sensor_ts ON telemetry (sensor_id, ts DESC);
        CREATE INDEX idx_telemetry_site_ts   ON telemetry (site_id,   ts DESC);
        """
    )

    # ------------------------------------------------------------------
    # Alarms + alarm rules
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE alarms (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            opened_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
            site_id         UUID NOT NULL REFERENCES sites(id)   ON DELETE CASCADE,
            asset_id        UUID NOT NULL REFERENCES assets(id)  ON DELETE CASCADE,
            sensor_id       UUID          REFERENCES sensors(id) ON DELETE SET NULL,
            code            TEXT NOT NULL,
            severity        alarm_severity NOT NULL,
            state           alarm_state    NOT NULL DEFAULT 'OPEN',
            message         TEXT NOT NULL,
            triggered_value DOUBLE PRECISION,
            threshold_value DOUBLE PRECISION,
            acked_at        TIMESTAMPTZ,
            acked_by        UUID REFERENCES users(id) ON DELETE SET NULL,
            ack_note        TEXT,
            resolved_at     TIMESTAMPTZ,
            resolved_by     UUID REFERENCES users(id) ON DELETE SET NULL,
            resolve_note    TEXT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at      TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX idx_alarms_state_opened ON alarms(state, opened_at DESC);
        CREATE INDEX idx_alarms_asset_state  ON alarms(asset_id, state);
        CREATE INDEX idx_alarms_severity     ON alarms(severity);
        CREATE INDEX idx_alarms_site_state   ON alarms(site_id, state);
        CREATE UNIQUE INDEX uq_alarms_open_per_asset_code
            ON alarms(asset_id, code) WHERE state = 'OPEN';
        """
    )

    op.execute(
        """
        CREATE TABLE alarm_rules (
            id                UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            sensor_id         UUID NOT NULL REFERENCES sensors(id) ON DELETE CASCADE,
            code              TEXT NOT NULL,
            severity          alarm_severity NOT NULL,
            comparator        TEXT NOT NULL CHECK (comparator IN ('gt','gte','lt','lte','eq')),
            threshold_value   DOUBLE PRECISION NOT NULL,
            message_template  TEXT NOT NULL,
            is_active         BOOLEAN NOT NULL DEFAULT TRUE,
            created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            updated_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
            CONSTRAINT uq_alarm_rules_sensor_code UNIQUE (sensor_id, code)
        );
        CREATE INDEX idx_alarm_rules_sensor ON alarm_rules(sensor_id);
        """
    )

    # ------------------------------------------------------------------
    # Asset status history
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE asset_status_history (
            id          UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            asset_id    UUID NOT NULL REFERENCES assets(id) ON DELETE CASCADE,
            status      asset_status NOT NULL,
            reason      TEXT,
            ts          TIMESTAMPTZ NOT NULL DEFAULT now()
        );
        CREATE INDEX idx_status_hist_asset_ts ON asset_status_history(asset_id, ts DESC);
        """
    )

    # ------------------------------------------------------------------
    # Audit log (column names per the data-track prompt)
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE audit_log (
            id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            "timestamp"   TIMESTAMPTZ NOT NULL DEFAULT now(),
            user_id       UUID REFERENCES users(id) ON DELETE SET NULL,
            actor_email   TEXT NOT NULL,
            action        TEXT NOT NULL,
            entity_type   TEXT,
            entity_id     UUID,
            details_json  JSONB NOT NULL DEFAULT '{}'::jsonb
        );
        CREATE INDEX idx_audit_ts        ON audit_log("timestamp" DESC);
        CREATE INDEX idx_audit_user_ts   ON audit_log(user_id, "timestamp" DESC);
        CREATE INDEX idx_audit_action    ON audit_log(action);
        CREATE INDEX idx_audit_entity    ON audit_log(entity_type, entity_id);
        """
    )

    # ------------------------------------------------------------------
    # Reports
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE TABLE reports (
            id              UUID PRIMARY KEY DEFAULT gen_random_uuid(),
            kind            TEXT NOT NULL,
            format          report_format NOT NULL,
            status          report_status NOT NULL DEFAULT 'queued',
            params          JSONB NOT NULL,
            file_path       TEXT,
            file_size_bytes BIGINT,
            error           TEXT,
            created_by      UUID NOT NULL REFERENCES users(id) ON DELETE RESTRICT,
            created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
            finished_at     TIMESTAMPTZ
        );
        CREATE INDEX idx_reports_creator_ts ON reports(created_by, created_at DESC);
        CREATE INDEX idx_reports_status     ON reports(status);
        """
    )

    # ------------------------------------------------------------------
    # Continuous aggregate: 5-minute buckets for fast chart queries.
    # Kept simple � one view, no policy. Add a refresh policy in a later
    # migration if/when production traffic demands it.
    # ------------------------------------------------------------------
    op.execute(
        """
        CREATE MATERIALIZED VIEW telemetry_5m
        WITH (timescaledb.continuous) AS
        SELECT
            time_bucket('5 minutes', ts) AS bucket,
            asset_id,
            sensor_id,
            metric,
            AVG(value) AS avg_value,
            MIN(value) AS min_value,
            MAX(value) AS max_value,
            LAST(value, ts) AS last_value
        FROM telemetry
        GROUP BY bucket, asset_id, sensor_id, metric
        WITH NO DATA;
        """
    )


def downgrade() -> None:
    # Single-revision baseline. Downgrade tears the whole schema down.
    op.execute("DROP MATERIALIZED VIEW IF EXISTS telemetry_5m CASCADE;")
    op.execute("DROP TABLE IF EXISTS reports         CASCADE;")
    op.execute("DROP TABLE IF EXISTS audit_log       CASCADE;")
    op.execute("DROP TABLE IF EXISTS asset_status_history CASCADE;")
    op.execute("DROP TABLE IF EXISTS alarm_rules     CASCADE;")
    op.execute("DROP TABLE IF EXISTS alarms          CASCADE;")
    op.execute("DROP TABLE IF EXISTS telemetry       CASCADE;")
    op.execute("DROP TABLE IF EXISTS users           CASCADE;")
    op.execute("DROP TABLE IF EXISTS sensors         CASCADE;")
    op.execute("DROP TABLE IF EXISTS assets          CASCADE;")
    op.execute("DROP TABLE IF EXISTS areas           CASCADE;")
    op.execute("DROP TABLE IF EXISTS sites           CASCADE;")
    op.execute("DROP TABLE IF EXISTS companies       CASCADE;")

    op.execute("DROP TYPE IF EXISTS report_format;")
    op.execute("DROP TYPE IF EXISTS report_status;")
    op.execute("DROP TYPE IF EXISTS telemetry_quality;")
    op.execute("DROP TYPE IF EXISTS alarm_severity;")
    op.execute("DROP TYPE IF EXISTS alarm_state;")
    op.execute("DROP TYPE IF EXISTS asset_status;")
    op.execute("DROP TYPE IF EXISTS user_role;")
