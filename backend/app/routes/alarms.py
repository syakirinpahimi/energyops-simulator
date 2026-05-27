"""Alarm routes: list, fetch, acknowledge, resolve."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Optional
from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, status
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import get_current_user, roles_at_least
from app.models import Alarm, Asset, Sensor, User
from app.schemas import AlarmAckRequest, AlarmList, AlarmOut
from app.services.audit import write_audit


def _hydrate(db: Session, alarm: Alarm) -> AlarmOut:
    """Build an ``AlarmOut`` enriched with asset/sensor names + ack actor email.

    The base ORM row only has ids; the alarms table on the wire is more useful
    when it carries the human-readable names too. We do these lookups one row
    at a time which is fine for the small page sizes the UI requests.
    """
    asset_name: Optional[str] = None
    sensor_name: Optional[str] = None
    acked_by_email: Optional[str] = None
    resolved_by_email: Optional[str] = None
    if alarm.asset_id:
        asset = db.get(Asset, alarm.asset_id)
        asset_name = asset.name if asset else None
    if alarm.sensor_id:
        sensor = db.get(Sensor, alarm.sensor_id)
        sensor_name = sensor.metric if sensor else None
    if alarm.acked_by:
        acker = db.get(User, alarm.acked_by)
        acked_by_email = acker.email if acker else None
    if alarm.resolved_by:
        resolver = db.get(User, alarm.resolved_by)
        resolved_by_email = resolver.email if resolver else None
    return AlarmOut(
        id=alarm.id,
        asset_id=alarm.asset_id,
        asset_name=asset_name,
        sensor_id=alarm.sensor_id,
        sensor_name=sensor_name,
        code=alarm.code,
        severity=alarm.severity,
        message=alarm.message,
        state=alarm.state,
        triggered_value=alarm.triggered_value,
        threshold_value=alarm.threshold_value,
        opened_at=alarm.opened_at,
        acked_at=alarm.acked_at,
        acked_by=alarm.acked_by,
        acked_by_email=acked_by_email,
        ack_note=alarm.ack_note,
        resolved_at=alarm.resolved_at,
        resolved_by=alarm.resolved_by,
        resolved_by_email=resolved_by_email,
        resolve_note=alarm.resolve_note,
    )

router = APIRouter(prefix="/alarms", tags=["alarms"])


def _alarm_not_found(alarm_id: UUID) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_404_NOT_FOUND,
        detail={
            "error": {
                "code": "ALARM_NOT_FOUND",
                "message": f"Alarm {alarm_id} does not exist",
                "details": {"alarm_id": str(alarm_id)},
            }
        },
    )


def _conflict(message: str, **details) -> HTTPException:
    return HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={"error": {"code": "ALARM_STATE_CONFLICT", "message": message, "details": details}},
    )


@router.get("", response_model=AlarmList)
def list_alarms(
    state: Optional[str] = Query(default=None, pattern="^(OPEN|ACK|RESOLVED)$"),
    asset_id: Optional[UUID] = Query(default=None),
    severity: Optional[str] = Query(default=None, pattern="^(info|warning|critical)$"),
    limit: int = Query(default=50, ge=1, le=500),
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AlarmList:
    """List alarms, most recent first."""
    stmt = select(Alarm).order_by(Alarm.opened_at.desc()).limit(limit)
    if state is not None:
        stmt = stmt.where(Alarm.state == state)
    if asset_id is not None:
        stmt = stmt.where(Alarm.asset_id == asset_id)
    if severity is not None:
        stmt = stmt.where(Alarm.severity == severity)
    rows = db.scalars(stmt).all()
    return AlarmList(items=[_hydrate(db, r) for r in rows])


@router.get("/{alarm_id}", response_model=AlarmOut)
def get_alarm(
    alarm_id: UUID,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AlarmOut:
    alarm = db.get(Alarm, alarm_id)
    if alarm is None:
        raise _alarm_not_found(alarm_id)
    return _hydrate(db, alarm)


@router.post("/{alarm_id}/acknowledge", response_model=AlarmOut)
@router.post("/{alarm_id}/ack", response_model=AlarmOut, include_in_schema=False)
def acknowledge_alarm(
    alarm_id: UUID,
    payload: Optional[AlarmAckRequest] = None,
    db: Session = Depends(get_db),
    user: User = Depends(get_current_user),
) -> AlarmOut:
    """Acknowledge an OPEN alarm. Operator+ allowed.

    Both ``/acknowledge`` (user-requested path) and ``/ack`` (per
    docs/API_CONTRACT.md) are accepted; the second is hidden from OpenAPI
    to keep the schema clean.
    """
    alarm = db.get(Alarm, alarm_id)
    if alarm is None:
        raise _alarm_not_found(alarm_id)
    if alarm.state != "OPEN":
        raise _conflict(
            f"Cannot acknowledge alarm in state {alarm.state}",
            alarm_id=str(alarm_id),
            state=alarm.state,
        )

    note = payload.note if payload else None
    alarm.state = "ACK"
    alarm.acked_at = datetime.now(timezone.utc)
    alarm.acked_by = user.id
    alarm.ack_note = note

    write_audit(
        db,
        actor=user,
        action="alarm.ack",
        target_type="alarm",
        target_id=alarm.id,
        metadata={
            "note": note,
            "asset_id": str(alarm.asset_id),
            "code": alarm.code,
            "severity": alarm.severity,
        },
    )
    db.commit()
    db.refresh(alarm)
    return _hydrate(db, alarm)


_RESOLVE_GUARD = roles_at_least("engineer")


@router.post("/{alarm_id}/resolve", response_model=AlarmOut)
def resolve_alarm(
    alarm_id: UUID,
    payload: Optional[AlarmAckRequest] = None,
    db: Session = Depends(get_db),
    user: User = Depends(_RESOLVE_GUARD),
) -> AlarmOut:
    """Resolve an OPEN or ACK'd alarm. Engineer+ only."""
    alarm = db.get(Alarm, alarm_id)
    if alarm is None:
        raise _alarm_not_found(alarm_id)
    if alarm.state == "RESOLVED":
        raise _conflict("Alarm already resolved", alarm_id=str(alarm_id), state=alarm.state)

    note = payload.note if payload else None
    alarm.state = "RESOLVED"
    alarm.resolved_at = datetime.now(timezone.utc)
    alarm.resolved_by = user.id
    alarm.resolve_note = note

    write_audit(
        db,
        actor=user,
        action="alarm.resolve",
        target_type="alarm",
        target_id=alarm.id,
        metadata={
            "note": note,
            "asset_id": str(alarm.asset_id),
            "code": alarm.code,
        },
    )
    db.commit()
    db.refresh(alarm)
    return _hydrate(db, alarm)
