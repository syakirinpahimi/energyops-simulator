"""Health and root status routes."""
from __future__ import annotations

from fastapi import APIRouter

from app import __version__
from app.db import ping_db
from app.schemas import HealthOut

router = APIRouter(tags=["health"])


@router.get("/health", response_model=HealthOut)
def health() -> HealthOut:
    """Liveness + DB connectivity probe.

    Returns ``status: ok`` when the DB is reachable and ``status: degraded``
    when it is not. The route never raises so orchestrators can rely on it.
    """
    db_up = ping_db()
    return HealthOut(
        status="ok" if db_up else "degraded",
        version=__version__,
        db="up" if db_up else "down",
    )
