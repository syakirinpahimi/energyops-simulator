"""Alarm acknowledgement + audit trail tests (need real DB + seed)."""
from __future__ import annotations

from uuid import UUID

from fastapi.testclient import TestClient

from tests.conftest import needs_db


def _auth(token: str) -> dict:
    return {"Authorization": f"Bearer {token}"}


def _first_open_alarm_id() -> str:
    from app.db import session_scope
    from app.models import Alarm

    with session_scope() as db:
        alarm = db.query(Alarm).filter(Alarm.state == "OPEN").first()
        assert alarm is not None, "seed should produce at least one OPEN alarm"
        return str(alarm.id)


@needs_db
def test_acknowledge_alarm_writes_audit_log(client: TestClient, operator_token: str) -> None:
    """Acknowledging an alarm must persist an ``alarm.ack`` audit row.

    We snapshot the count before/after and also assert the row carries the
    actor email + alarm id so the audit page can render something useful.
    """
    from app.db import session_scope
    from app.models import AuditLog

    alarm_id = _first_open_alarm_id()
    h = _auth(operator_token)

    with session_scope() as db:
        before = db.query(AuditLog).filter(AuditLog.action == "alarm.ack").count()

    resp = client.post(
        f"/alarms/{alarm_id}/acknowledge",
        headers=h,
        json={"note": "looking now"},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["state"] == "ACK"
    assert body["acked_by"] is not None
    assert body["asset_name"]  # hydration is wired up

    with session_scope() as db:
        after = db.query(AuditLog).filter(AuditLog.action == "alarm.ack").count()
        assert after == before + 1, "alarm.ack should write exactly one audit row"
        latest = (
            db.query(AuditLog)
            .filter(AuditLog.action == "alarm.ack")
            .order_by(AuditLog.timestamp.desc())
            .first()
        )
        assert latest is not None
        assert latest.entity_type == "alarm"
        assert str(latest.entity_id) == alarm_id
        assert latest.actor_email
        assert latest.details_json.get("note") == "looking now"

    # Operators cannot read the audit log.
    audit = client.get("/audit-log?action=alarm.ack", headers=h)
    assert audit.status_code == 403


@needs_db
def test_double_ack_returns_409(client: TestClient, operator_token: str) -> None:
    alarm_id = _first_open_alarm_id()
    h = _auth(operator_token)

    first = client.post(f"/alarms/{alarm_id}/acknowledge", headers=h, json={})
    assert first.status_code == 200
    second = client.post(f"/alarms/{alarm_id}/acknowledge", headers=h, json={})
    assert second.status_code == 409
    assert second.json()["error"]["code"] == "ALARM_STATE_CONFLICT"


@needs_db
def test_audit_log_visible_to_manager(client: TestClient, manager_token: str) -> None:
    h = _auth(manager_token)
    resp = client.get("/audit-log", headers=h)
    assert resp.status_code == 200
    assert "items" in resp.json()
