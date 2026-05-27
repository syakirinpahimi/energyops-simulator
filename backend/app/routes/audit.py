"""Audit log read endpoint. Engineer+ only."""
from __future__ import annotations

from datetime import datetime
from typing import Optional
from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import get_db
from app.deps import roles_at_least
from app.models import AuditLog, User
from app.schemas import AuditEntryOut, AuditList

router = APIRouter(tags=["audit"])

_AUDIT_GUARD = roles_at_least("engineer")


@router.get("/audit-log", response_model=AuditList)
@router.get("/audit", response_model=AuditList, include_in_schema=False)
def list_audit(
    actor_id: Optional[UUID] = Query(default=None),
    action: Optional[str] = Query(default=None),
    start: Optional[datetime] = Query(default=None, alias="from"),
    end: Optional[datetime] = Query(default=None, alias="to"),
    limit: int = Query(default=100, ge=1, le=1000),
    db: Session = Depends(get_db),
    user: User = Depends(_AUDIT_GUARD),
) -> AuditList:
    """List audit entries, most recent first.

    Both ``/audit-log`` (user spec) and ``/audit`` (API contract) work.
    """
    stmt = select(AuditLog).order_by(AuditLog.timestamp.desc()).limit(limit)
    if actor_id is not None:
        stmt = stmt.where(AuditLog.user_id == actor_id)
    if action is not None:
        stmt = stmt.where(AuditLog.action == action)
    if start is not None:
        stmt = stmt.where(AuditLog.timestamp >= start)
    if end is not None:
        stmt = stmt.where(AuditLog.timestamp < end)
    rows = db.scalars(stmt).all()
    return AuditList(items=[AuditEntryOut.from_row(r) for r in rows])
