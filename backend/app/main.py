"""FastAPI application entry point."""
from __future__ import annotations

import logging
import os
from contextlib import asynccontextmanager
from typing import AsyncIterator, Optional

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from sqlalchemy.exc import OperationalError, SQLAlchemyError
from starlette.exceptions import HTTPException as StarletteHTTPException

from app import __version__
from app.config import get_settings
from app.db import init_db_tables
from app.routes import alarms, audit, auth, health, hierarchy, reports, telemetry, ws
from app.services.ws_hub import hub as ws_hub

log = logging.getLogger(__name__)


def _mqtt_enabled() -> bool:
    """Allow tests / local runs to disable the consumer cleanly.

    Set ``MQTT_ENABLED=0`` (or ``false``/``no``) to skip the background
    subscriber. Useful for unit tests and laptop dev without a broker.
    """
    raw = os.getenv("MQTT_ENABLED", "1").strip().lower()
    return raw not in ("0", "false", "no", "off", "")


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Bootstrap the schema and start the MQTT consumer.

    Both steps are best-effort: a broker or DB that is briefly unavailable
    must not crash the API. The consumer's paho client retries connection
    internally; if construction itself fails (e.g. paho missing), we log
    and continue so the REST surface still serves.
    """
    try:
        init_db_tables()
        log.info("DB tables ensured")
    except Exception as exc:  # noqa: BLE001
        log.warning("DB unavailable at startup, continuing: %s", exc)

    consumer = None
    if _mqtt_enabled():
        try:
            from app.services.mqtt_consumer import MqttConsumer

            consumer = MqttConsumer(broadcast=ws_hub.broadcast)
            await consumer.start()
            log.info("MQTT consumer attached to lifespan")
        except Exception as exc:  # noqa: BLE001
            log.warning("MQTT consumer not started, continuing: %s", exc)
            consumer = None
    else:
        log.info("MQTT consumer disabled via MQTT_ENABLED env")

    # Stash on app.state so tests can inspect / replace it.
    app.state.mqtt_consumer = consumer

    try:
        yield
    finally:
        if consumer is not None:
            try:
                await consumer.stop()
                log.info("MQTT consumer stopped")
            except Exception as exc:  # noqa: BLE001
                log.warning("error stopping MQTT consumer: %s", exc)


def create_app() -> FastAPI:
    settings = get_settings()
    logging.basicConfig(
        level=settings.log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )

    app = FastAPI(
        title="EnergyOps Backend",
        version=__version__,
        docs_url="/docs",
        redoc_url="/redoc",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    # Routes that match the user's path list directly.
    app.include_router(health.router)
    app.include_router(auth.router)
    app.include_router(hierarchy.router)
    app.include_router(telemetry.router)
    app.include_router(alarms.router)
    app.include_router(reports.router)
    app.include_router(audit.router)
    app.include_router(ws.router)

    # Versioned mirror at /api/v1/* per the frozen contract. Same routers,
    # so OpenAPI shows both. Frontend should target /api/v1.
    api_v1_prefix = "/api/v1"
    app.include_router(health.router, prefix=api_v1_prefix, include_in_schema=False)
    app.include_router(auth.router, prefix=api_v1_prefix, include_in_schema=False)
    app.include_router(hierarchy.router, prefix=api_v1_prefix, include_in_schema=False)
    app.include_router(telemetry.router, prefix=api_v1_prefix, include_in_schema=False)
    app.include_router(alarms.router, prefix=api_v1_prefix, include_in_schema=False)
    app.include_router(reports.router, prefix=api_v1_prefix, include_in_schema=False)
    app.include_router(audit.router, prefix=api_v1_prefix, include_in_schema=False)

    _register_error_handlers(app)
    return app


def _register_error_handlers(app: FastAPI) -> None:
    """Wrap framework errors in the {error: {code, message, details}} envelope."""

    @app.exception_handler(StarletteHTTPException)
    async def _http_exc(_: Request, exc: StarletteHTTPException) -> JSONResponse:
        # Detail may already be the envelope (we built it that way in routes)
        # or a plain string from FastAPI default behaviour.
        if isinstance(exc.detail, dict) and "error" in exc.detail:
            return JSONResponse(status_code=exc.status_code, content=exc.detail)
        return JSONResponse(
            status_code=exc.status_code,
            content={
                "error": {
                    "code": _code_for_status(exc.status_code),
                    "message": str(exc.detail),
                }
            },
        )

    @app.exception_handler(RequestValidationError)
    async def _validation_exc(_: Request, exc: RequestValidationError) -> JSONResponse:
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content={
                "error": {
                    "code": "VALIDATION_ERROR",
                    "message": "Request validation failed",
                    "details": {"errors": exc.errors()},
                }
            },
        )

    @app.exception_handler(OperationalError)
    async def _db_unavailable(_: Request, exc: OperationalError) -> JSONResponse:
        log.error("DB operational error: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            content={
                "error": {
                    "code": "DB_UNAVAILABLE",
                    "message": "Database is unavailable; please retry shortly",
                }
            },
        )

    @app.exception_handler(SQLAlchemyError)
    async def _db_error(_: Request, exc: SQLAlchemyError) -> JSONResponse:
        log.exception("DB error: %s", exc)
        return JSONResponse(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            content={"error": {"code": "DB_ERROR", "message": "A database error occurred"}},
        )


def _code_for_status(code: int) -> str:
    return {
        400: "BAD_REQUEST",
        401: "UNAUTHENTICATED",
        403: "FORBIDDEN",
        404: "NOT_FOUND",
        409: "CONFLICT",
        422: "VALIDATION_ERROR",
        500: "INTERNAL_ERROR",
        503: "SERVICE_UNAVAILABLE",
    }.get(code, "ERROR")


app = create_app()
