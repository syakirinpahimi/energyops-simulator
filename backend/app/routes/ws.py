"""WebSocket endpoint for live telemetry/alarm broadcasts.

The contract from docs/API_CONTRACT.md uses ``/ws/telemetry``; we expose
that path and accept ``token`` as a query parameter (browsers cannot send
custom headers on WS upgrade).

For MVP this endpoint accepts a JWT and registers the socket with the
in-memory hub. Pushes happen from elsewhere (alarm ack handler, MQTT
subscriber) by calling ``hub.broadcast``. The MQTT subscriber that turns
upstream messages into broadcasts is a separate task -- TODO(backend).
"""
from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone
from typing import Optional

from fastapi import APIRouter, Query, WebSocket, WebSocketDisconnect

from app.security import JWTError, decode_access_token
from app.services.ws_hub import hub

log = logging.getLogger(__name__)

router = APIRouter(tags=["ws"])

# Custom WS close codes per API contract.
_WS_INVALID_TOKEN = 4401


def _validate_token(token: Optional[str]) -> Optional[dict]:
    if not token:
        return None
    try:
        return decode_access_token(token)
    except JWTError as exc:
        log.info("ws: rejecting invalid token: %s", exc)
        return None


@router.websocket("/ws/telemetry")
@router.websocket("/stream/telemetry")
async def ws_telemetry(ws: WebSocket, token: Optional[str] = Query(default=None)) -> None:
    """Long-lived WS connection. Sends ``ping`` every 30s.

    Both ``/ws/telemetry`` (contract) and ``/stream/telemetry`` (alias from
    user spec) are accepted.
    """
    payload = _validate_token(token)
    if payload is None:
        await ws.close(code=_WS_INVALID_TOKEN)
        return

    await ws.accept()
    await hub.connect(ws)
    log.info("ws: client connected (user=%s)", payload.get("email"))

    async def _heartbeat() -> None:
        while True:
            await asyncio.sleep(30)
            await ws.send_json({"type": "ping", "ts": datetime.now(timezone.utc).isoformat()})

    hb_task = asyncio.create_task(_heartbeat())
    try:
        while True:
            # We accept subscribe/unsubscribe/pong messages but the MVP hub
            # broadcasts to every socket. Filtering is a TODO(backend).
            msg = await ws.receive_json()
            if isinstance(msg, dict) and msg.get("type") == "pong":
                continue
            # Echo unknown messages at debug to aid client development.
            log.debug("ws: ignored client message: %r", msg)
    except WebSocketDisconnect:
        log.info("ws: client disconnected")
    except Exception as exc:  # noqa: BLE001
        log.warning("ws: error, closing: %s", exc)
    finally:
        hb_task.cancel()
        await hub.disconnect(ws)
