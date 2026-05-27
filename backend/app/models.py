"""SQLAlchemy ORM models.

Mirrors `docs/DATA_MODEL.md` table-for-table. Junior-readable: one class per
table, columns roughly in DDL order, FKs spelled out.

Conventions:
  - All ids are UUIDs with server-side `gen_random_uuid()`.
  - All timestamps are `TIMESTAMPTZ` with server default `now()`.
  - Enums are real Postgres enums (created in the initial migration).

Note: TimescaleDB-specific things (hypertable conversion, continuous
aggregates, retention) live in the migration, not here -- SQLAlchemy doesn't
need to know about them.
"""

from __future__ import annotations

from sqlalchemy import (
    Boolean,
    CheckConstraint,
    Column,
    DateTime,
    Enum as SAEnum,
    Float,
    ForeignKey,
    Index,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, UUID

from app.db import Base


# --- enum value lists (match the Postgres enum types in 0001_initial) ---

USER_ROLES = ("operator", "engineer", "manager", "admin")
ASSET_STATUSES = ("online", "offline", "fault", "maintenance")
ALARM_STATES = ("OPEN", "ACK", "RESOLVED")
ALARM_SEVERITIES = ("info", "warning", "critical")
TELEMETRY_QUALITIES = ("good", "uncertain", "bad")
REPORT_STATUSES = ("queued", "running", "ready", "failed")
REPORT_FORMATS = ("csv", "pdf")


# Reusable column factories so every table looks consistent.
def _uuid_pk() -> Column:
    return Column(
        UUID(as_uuid=True),
        primary_key=True,
        server_default=text("gen_random_uuid()"),
    )


def _created_at() -> Column:
    return Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


def _updated_at() -> Column:
    return Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


# ============================================================================
# Hierarchy: company -> site -> area -> asset -> sensor
# ============================================================================


class Company(Base):
    __tablename__ = "companies"

    id = _uuid_pk()
    slug = Column(String, nullable=False, unique=True)
    name = Column(String, nullable=False)
    created_at = _created_at()


class Site(Base):
    __tablename__ = "sites"
    __table_args__ = (
        UniqueConstraint("company_id", "slug", name="uq_sites_company_slug"),
    )

    id = _uuid_pk()
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="CASCADE"),
        nullable=False,
    )
    slug = Column(String, nullable=False)
    name = Column(String, nullable=False)
    timezone = Column(
        String, nullable=False, server_default=text("'Asia/Kuala_Lumpur'")
    )
    location = Column(JSONB, nullable=True)  # { lat, lon, address }
    created_at = _created_at()


class Area(Base):
    __tablename__ = "areas"
    __table_args__ = (
        UniqueConstraint("site_id", "slug", name="uq_areas_site_slug"),
    )

    id = _uuid_pk()
    site_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sites.id", ondelete="CASCADE"),
        nullable=False,
    )
    slug = Column(String, nullable=False)
    name = Column(String, nullable=False)
    created_at = _created_at()


class Asset(Base):
    __tablename__ = "assets"
    __table_args__ = (
        UniqueConstraint("area_id", "slug", name="uq_assets_area_slug"),
        Index("idx_assets_area", "area_id"),
        Index("idx_assets_status", "status"),
        Index("idx_assets_type", "asset_type"),
    )

    id = _uuid_pk()
    area_id = Column(
        UUID(as_uuid=True),
        ForeignKey("areas.id", ondelete="CASCADE"),
        nullable=False,
    )
    slug = Column(String, nullable=False)
    name = Column(String, nullable=False)
    asset_type = Column(String, nullable=False)  # 'pump','compressor','chiller',...
    status = Column(
        SAEnum(*ASSET_STATUSES, name="asset_status", create_type=False),
        nullable=False,
        server_default=text("'offline'"),
    )
    rated_power_kw = Column(Numeric(10, 2), nullable=True)
    metadata_json = Column(
        "metadata", JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )
    created_at = _created_at()
    updated_at = _updated_at()


class Sensor(Base):
    __tablename__ = "sensors"
    __table_args__ = (
        UniqueConstraint("asset_id", "metric", name="uq_sensors_asset_metric"),
        Index("idx_sensors_asset", "asset_id"),
    )

    id = _uuid_pk()
    asset_id = Column(
        UUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
    )
    metric = Column(String, nullable=False)  # 'power_kw','temperature_c',...
    unit = Column(String, nullable=False)  # e.g. 'kW', 'C', 'V', 'mm/s'
    description = Column(Text, nullable=True)
    min_value = Column(Numeric, nullable=True)
    max_value = Column(Numeric, nullable=True)
    created_at = _created_at()


# ============================================================================
# Users
# ============================================================================


class User(Base):
    __tablename__ = "users"
    __table_args__ = (
        Index("idx_users_company", "company_id"),
        Index("idx_users_email_lower", text("lower(email)"), unique=True),
    )

    id = _uuid_pk()
    company_id = Column(
        UUID(as_uuid=True),
        ForeignKey("companies.id", ondelete="RESTRICT"),
        nullable=False,
    )
    # We use plain TEXT + a unique index on lower(email) so we don't depend
    # on the citext extension being available.
    email = Column(String, nullable=False)
    name = Column(String, nullable=False)
    password_hash = Column(String, nullable=False)
    role = Column(
        SAEnum(*USER_ROLES, name="user_role", create_type=False),
        nullable=False,
    )
    is_active = Column(Boolean, nullable=False, server_default=text("TRUE"))
    last_login_at = Column(DateTime(timezone=True), nullable=True)
    created_at = _created_at()
    updated_at = _updated_at()


# ============================================================================
# Telemetry (TimescaleDB hypertable)
# ============================================================================
#
# We expose two ORM views of the same physical table so both names work:
#   - Telemetry:        the canonical name from docs/DATA_MODEL.md
#   - TelemetryReading: the alias name used in the user prompt
#
# Both classes point at the same underlying table 'telemetry'. Most code
# should import Telemetry; TelemetryReading exists for ergonomic naming.


class Telemetry(Base):
    __tablename__ = "telemetry"
    __table_args__ = (
        # Composite PK is required for hypertables in Timescale.
        Index("idx_telemetry_asset_ts", "asset_id", text("ts DESC")),
        Index("idx_telemetry_metric_ts", "metric", text("ts DESC")),
        Index("idx_telemetry_sensor_ts", "sensor_id", text("ts DESC")),
        Index("idx_telemetry_site_ts", "site_id", text("ts DESC")),
    )

    # Hypertable partition column.
    ts = Column(DateTime(timezone=True), primary_key=True, nullable=False)

    # Denormalised hierarchy ids so dashboards can filter without joins.
    company_id = Column(UUID(as_uuid=True), nullable=False)
    site_id = Column(UUID(as_uuid=True), nullable=False)
    area_id = Column(UUID(as_uuid=True), nullable=False)
    asset_id = Column(UUID(as_uuid=True), nullable=False)
    sensor_id = Column(UUID(as_uuid=True), primary_key=True, nullable=False)

    metric = Column(String, nullable=False)
    value = Column(Float, nullable=False)
    unit = Column(String, nullable=False)
    quality = Column(
        SAEnum(*TELEMETRY_QUALITIES, name="telemetry_quality", create_type=False),
        nullable=False,
        server_default=text("'good'"),
    )


# ============================================================================
# Alarms + Alarm rules
# ============================================================================


class Alarm(Base):
    __tablename__ = "alarms"
    __table_args__ = (
        Index("idx_alarms_state_opened", "state", text("opened_at DESC")),
        Index("idx_alarms_asset_state", "asset_id", "state"),
        Index("idx_alarms_severity", "severity"),
        Index("idx_alarms_site_state", "site_id", "state"),
        # One OPEN alarm per (asset, code) at a time. Built in the migration
        # as a partial index; declared here for documentation only.
    )

    id = _uuid_pk()

    # 'opened_at' matches the frozen docs; 'timestamp' from the user prompt is
    # available as a property on the model if other code wants it.
    opened_at = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )

    site_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sites.id", ondelete="CASCADE"),
        nullable=False,
    )
    asset_id = Column(
        UUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
    )
    sensor_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sensors.id", ondelete="SET NULL"),
        nullable=True,
    )

    code = Column(String, nullable=False)  # 'TEMP_HIGH','POWER_LOST',...
    severity = Column(
        SAEnum(*ALARM_SEVERITIES, name="alarm_severity", create_type=False),
        nullable=False,
    )
    state = Column(
        SAEnum(*ALARM_STATES, name="alarm_state", create_type=False),
        nullable=False,
        server_default=text("'OPEN'"),
    )
    message = Column(Text, nullable=False)

    triggered_value = Column(Float, nullable=True)
    threshold_value = Column(Float, nullable=True)

    acked_at = Column(DateTime(timezone=True), nullable=True)
    acked_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    ack_note = Column(Text, nullable=True)

    resolved_at = Column(DateTime(timezone=True), nullable=True)
    resolved_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    resolve_note = Column(Text, nullable=True)

    created_at = _created_at()
    updated_at = _updated_at()


class AlarmRule(Base):
    """Threshold rule for generating alarms (used by backend rule engine).

    Not in the original frozen DATA_MODEL.md; added per the data-track prompt.
    Kept simple: one rule per (sensor, comparator, threshold).
    """

    __tablename__ = "alarm_rules"
    __table_args__ = (
        UniqueConstraint("sensor_id", "code", name="uq_alarm_rules_sensor_code"),
        Index("idx_alarm_rules_sensor", "sensor_id"),
    )

    id = _uuid_pk()
    sensor_id = Column(
        UUID(as_uuid=True),
        ForeignKey("sensors.id", ondelete="CASCADE"),
        nullable=False,
    )
    code = Column(String, nullable=False)  # 'TEMP_HIGH', 'PRESSURE_LOW', ...
    severity = Column(
        SAEnum(*ALARM_SEVERITIES, name="alarm_severity", create_type=False),
        nullable=False,
    )
    # 'gt' | 'gte' | 'lt' | 'lte' | 'eq'
    comparator = Column(String, nullable=False)
    threshold_value = Column(Float, nullable=False)
    message_template = Column(Text, nullable=False)
    is_active = Column(Boolean, nullable=False, server_default=text("TRUE"))
    created_at = _created_at()
    updated_at = _updated_at()


# ============================================================================
# Asset status history (kept from frozen docs; useful for uptime queries)
# ============================================================================


class AssetStatusHistory(Base):
    __tablename__ = "asset_status_history"
    __table_args__ = (
        Index("idx_status_hist_asset_ts", "asset_id", text("ts DESC")),
    )

    id = _uuid_pk()
    asset_id = Column(
        UUID(as_uuid=True),
        ForeignKey("assets.id", ondelete="CASCADE"),
        nullable=False,
    )
    status = Column(
        SAEnum(*ASSET_STATUSES, name="asset_status", create_type=False),
        nullable=False,
    )
    reason = Column(Text, nullable=True)
    ts = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )


# ============================================================================
# Audit log
# ============================================================================


class AuditLog(Base):
    """Append-only record of user-driven actions.

    Column names follow the user prompt:
      - timestamp     (when the action happened)
      - user_id       (actor)
      - action        (e.g. 'alarm.ack')
      - entity_type   (e.g. 'alarm','asset')
      - entity_id
      - details_json  (free-form structured detail)
    """

    __tablename__ = "audit_log"
    __table_args__ = (
        Index("idx_audit_ts", text("\"timestamp\" DESC")),
        Index("idx_audit_user_ts", "user_id", text("\"timestamp\" DESC")),
        Index("idx_audit_action", "action"),
        Index("idx_audit_entity", "entity_type", "entity_id"),
    )

    id = _uuid_pk()
    timestamp = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=text("now()"),
    )
    user_id = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="SET NULL"),
        nullable=True,
    )
    actor_email = Column(String, nullable=False)  # denormalised
    action = Column(String, nullable=False)
    entity_type = Column(String, nullable=True)
    entity_id = Column(UUID(as_uuid=True), nullable=True)
    details_json = Column(
        JSONB, nullable=False, server_default=text("'{}'::jsonb")
    )


# ============================================================================
# Reports
# ============================================================================


class Report(Base):
    __tablename__ = "reports"
    __table_args__ = (
        Index("idx_reports_creator_ts", "created_by", text("created_at DESC")),
        Index("idx_reports_status", "status"),
    )

    id = _uuid_pk()
    kind = Column(String, nullable=False)  # 'energy','alarms','uptime'
    format = Column(
        SAEnum(*REPORT_FORMATS, name="report_format", create_type=False),
        nullable=False,
    )
    status = Column(
        SAEnum(*REPORT_STATUSES, name="report_status", create_type=False),
        nullable=False,
        server_default=text("'queued'"),
    )
    params = Column(JSONB, nullable=False)
    file_path = Column(Text, nullable=True)
    file_size_bytes = Column(Integer, nullable=True)
    error = Column(Text, nullable=True)
    created_by = Column(
        UUID(as_uuid=True),
        ForeignKey("users.id", ondelete="RESTRICT"),
        nullable=False,
    )
    created_at = _created_at()
    finished_at = Column(DateTime(timezone=True), nullable=True)


# Convenience alias requested by the data-track prompt.
TelemetryReading = Telemetry
