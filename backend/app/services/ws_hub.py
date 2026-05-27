"""In-memory WebSocket hub.

Keeps a set of connected sockets so background tasks (MQTT subscriber,
alarm acknowledgement, etc.) can broadcast events without each route
knowing about every connection.

TODO(future): swap for Redis pub/sub when scaling beyond one process.
"""
from __future__ import annotations

import asyncio
import logging
from typing import Any, Dict, Set

from fastapi import WebSocket

log = logging.getLogger(__name__)


class WSHub:
    def __init__(self) -> None:
        self._sockets: Set[WebSocket] = set()
        self._lock = asyncio.Lock()

    async def connect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._sockets.add(ws)

    async def disconnect(self, ws: WebSocket) -> None:
        async with self._lock:
            self._sockets.discard(ws)

    async def broadcast(self, payload: Dict[str, Any]) -> None:
        """Send ``payload`` as JSON to every connected socket. Drops dead ones."""
        async with self._lock:
            snapshot = list(self._sockets)
        dead: list[WebSocket] = []
        for ws in snapshot:
            try:
                await ws.send_json(payload)
            except Exception as exc:  # noqa: BLE001
                log.debug("dropping ws on send failure: %s", exc)
                dead.append(ws)
        if dead:
            async with self._lock:
                for ws in dead:
                    self._sockets.discard(ws)

    @property
    def size(self) -> int:
        return len(self._sockets)


hub = WSHub()
