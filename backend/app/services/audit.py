"""Audit log writer.

The audit log is append-only. Always go through ``write_audit`` so we keep
the actor email denormalised and the metadata shape consistent.

Column names follow ``models.AuditLog`` (``timestamp``, ``user_id``,
``actor_email``, ``action``, ``entity_type``, ``entity_id``, ``details_json``).
"""
from __future__ import annotations

from typing import Any, Dict, Optional
from uuid import UUID

from sqlalchemy.orm import Session

from app.models import AuditLog, User


def write_audit(
    db: Session,
    *,
    actor: Optional[User],
    actor_email: Optional[str] = None,
    action: str,
    target_type: Optional[str] = None,
    target_id: Optional[UUID] = None,
    metadata: Optional[Dict[str, Any]] = None,
) -> AuditLog:
    """Insert an audit_log row and flush. Caller commits the surrounding txn.

    ``actor`` may be None for unauthenticated events (e.g. failed logins);
    in that case ``actor_email`` should carry the attempted address.
    """
    entry = AuditLog(
        user_id=actor.id if actor else None,
        actor_email=(actor.email if actor else (actor_email or "anonymous")),
        action=action,
        entity_type=target_type,
        entity_id=target_id,
        details_json=metadata or {},
    )
    db.add(entry)
    db.flush()
    return entry
