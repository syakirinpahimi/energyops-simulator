"""Pydantic v2 schemas for request/response validation.

Split into one file for readability since the API surface is small.
"""
from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, List, Literal, Optional
from uuid import UUID

from pydantic import BaseModel, ConfigDict, EmailStr, Field

# ---------------------------------------------------------------------------
# Common
# ---------------------------------------------------------------------------

Role = Literal["operator", "engineer", "manager", "admin"]
AssetStatus = Literal["online", "offline", "fault", "maintenance"]
AlarmState = Literal["OPEN", "ACK", "RESOLVED"]
AlarmSeverity = Literal["info", "warning", "critical"]
TelemetryQuality = Literal["good", "uncertain", "bad"]


class ORMModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ErrorDetail(BaseModel):
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None


class ErrorEnvelope(BaseModel):
    error: ErrorDetail


# ---------------------------------------------------------------------------
# Auth / users
# ---------------------------------------------------------------------------


class LoginRequest(BaseModel):
    # Plain string (not EmailStr) so demo accounts on `.local` (a reserved
    # TLD per email-validator >= 2.2) are accepted. The seed canonicalises
    # emails to lowercase; the auth route does the same on login.
    email: str = Field(min_length=3, max_length=254)
    password: str = Field(min_length=1)


class UserOut(ORMModel):
    id: UUID
    email: str
    name: str
    role: Role
    company_id: UUID
    created_at: datetime


class LoginResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"] = "bearer"
    user: UserOut


# ---------------------------------------------------------------------------
# Hierarchy
# ---------------------------------------------------------------------------


class CompanyOut(ORMModel):
    id: UUID
    slug: str
    name: str
    created_at: datetime


class SiteOut(ORMModel):
    id: UUID
    company_id: UUID
    slug: str
    name: str
    timezone: str
    location: Optional[Dict[str, Any]] = None
    created_at: datetime


class AreaOut(ORMModel):
    id: UUID
    site_id: UUID
    slug: str
    name: str
    created_at: datetime


class AssetOut(ORMModel):
    id: UUID
    area_id: UUID
    slug: str
    name: str
    asset_type: str
    status: AssetStatus
    rated_power_kw: Optional[float] = None
    metadata: Dict[str, Any] = Field(default_factory=dict, alias="metadata_json")
    created_at: datetime

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


class SensorOut(ORMModel):
    id: UUID
    asset_id: UUID
    metric: str
    unit: str
    description: Optional[str] = None
    min_value: Optional[float] = None
    max_value: Optional[float] = None
    created_at: datetime


# ---------------------------------------------------------------------------
# Telemetry
# ---------------------------------------------------------------------------


class TelemetryPoint(BaseModel):
    ts: datetime
    value: float


class TelemetryHistory(BaseModel):
    asset_id: UUID
    metric: str
    bucket: str
    agg: str
    points: List[TelemetryPoint]


class LatestReading(BaseModel):
    sensor_id: UUID
    metric: str
    unit: str
    value: float
    ts: datetime
    quality: TelemetryQuality = "good"


class AssetLatest(BaseModel):
    asset_id: UUID
    asset_name: str
    status: AssetStatus
    last_seen: Optional[datetime] = None
    readings: List[LatestReading]


# ---------------------------------------------------------------------------
# Alarms
# ---------------------------------------------------------------------------


class AlarmOut(ORMModel):
    id: UUID
    asset_id: UUID
    asset_name: Optional[str] = None
    sensor_id: Optional[UUID] = None
    sensor_name: Optional[str] = None
    code: str
    severity: AlarmSeverity
    message: str
    state: AlarmState
    triggered_value: Optional[float] = None
    threshold_value: Optional[float] = None
    opened_at: datetime
    acked_at: Optional[datetime] = None
    acked_by: Optional[UUID] = None
    acked_by_email: Optional[str] = None
    ack_note: Optional[str] = None
    resolved_at: Optional[datetime] = None
    resolved_by: Optional[UUID] = None
    resolved_by_email: Optional[str] = None
    resolve_note: Optional[str] = None


class AlarmAckRequest(BaseModel):
    note: Optional[str] = None


class AlarmList(BaseModel):
    items: List[AlarmOut]
    next_cursor: Optional[str] = None


# ---------------------------------------------------------------------------
# Audit
# ---------------------------------------------------------------------------


class AuditEntryOut(BaseModel):
    """Audit log row.

    The DB columns are ``timestamp``/``user_id``/``entity_type``/``entity_id``/
    ``details_json`` (see ``models.AuditLog``); we expose them under the
    contract names ``ts``/``actor_id``/``target_type``/``target_id``/
    ``metadata`` so the frontend has a stable shape.
    """

    id: UUID
    ts: datetime
    actor_id: Optional[UUID] = None
    actor_email: str
    action: str
    target_type: Optional[str] = None
    target_id: Optional[UUID] = None
    metadata: Dict[str, Any] = Field(default_factory=dict)

    model_config = ConfigDict(from_attributes=True)

    @classmethod
    def from_row(cls, row: Any) -> "AuditEntryOut":
        return cls(
            id=row.id,
            ts=row.timestamp,
            actor_id=row.user_id,
            actor_email=row.actor_email,
            action=row.action,
            target_type=row.entity_type,
            target_id=row.entity_id,
            metadata=row.details_json or {},
        )


class AuditList(BaseModel):
    items: List[AuditEntryOut]
    next_cursor: Optional[str] = None


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


class HealthOut(BaseModel):
    status: Literal["ok", "degraded"]
    version: str
    db: Literal["up", "down"]


__all__ = [
    "Role",
    "AssetStatus",
    "AlarmState",
    "AlarmSeverity",
    "TelemetryQuality",
    "ErrorDetail",
    "ErrorEnvelope",
    "LoginRequest",
    "UserOut",
    "LoginResponse",
    "CompanyOut",
    "SiteOut",
    "AreaOut",
    "AssetOut",
    "SensorOut",
    "TelemetryPoint",
    "TelemetryHistory",
    "LatestReading",
    "AssetLatest",
    "AlarmOut",
    "AlarmAckRequest",
    "AlarmList",
    "AuditEntryOut",
    "AuditList",
    "HealthOut",
]
