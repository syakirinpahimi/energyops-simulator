# Backend (FastAPI)

Owner track: `backend` (see `docs/AGENT_WORKFLOW.md`).

The backend is the only service that talks to PostgreSQL/TimescaleDB and to the MQTT broker. Everything else (frontend, simulator) goes through it or the broker.

## Responsibilities

- REST API per `docs/API_CONTRACT.md` (auth, hierarchy, telemetry history, alarms, reports, audit).
- WebSocket `/ws/telemetry` for live updates.
- MQTT subscriber background task that ingests telemetry/status/alarm/heartbeat and writes to the database.
- JWT auth + `require_role` enforcement.
- Report generation (CSV via stdlib, PDF via `reportlab`).
- Database migrations via Alembic.
- Seed script.

## Stack

- Python 3.11
- FastAPI + Uvicorn
- SQLAlchemy 2.x + asyncpg
- Alembic
- `pydantic-settings` for config
- `paho-mqtt` for the MQTT subscriber
- `passlib[bcrypt]` for password hashing
- `python-jose` for JWT
- `reportlab` for PDF
- `pytest`, `pytest-asyncio`, `httpx` for tests

## Suggested layout

```
backend/
├── Dockerfile
├── pyproject.toml
├── README.md                  # this file
├── STATUS.md                  # update before ending each session
├── alembic.ini
├── app/
│   ├── __init__.py
│   ├── main.py                # FastAPI app factory, lifespan hooks
│   ├── config.py              # pydantic-settings Settings class
│   ├── deps.py                # FastAPI dependencies (db session, current user, require_role)
│   ├── security.py            # password hashing, JWT encode/decode
│   ├── db.py                  # async engine, session factory
│   ├── models/                # SQLAlchemy models (one file per aggregate)
│   │   ├── __init__.py
│   │   ├── company.py
│   │   ├── hierarchy.py       # site, area, asset, sensor
│   │   ├── user.py
│   │   ├── telemetry.py
│   │   ├── alarm.py
│   │   ├── audit.py
│   │   └── report.py
│   ├── schemas/               # Pydantic request/response models — frontend reads these as ground truth
│   ├── routers/               # one router per resource group
│   │   ├── auth.py
│   │   ├── hierarchy.py
│   │   ├── telemetry.py
│   │   ├── alarms.py
│   │   ├── reports.py
│   │   └── audit.py
│   ├── services/              # business logic (no FastAPI imports here)
│   │   ├── alarms.py
│   │   ├── reports.py
│   │   └── audit.py
│   ├── mqtt/
│   │   ├── client.py          # paho-mqtt subscriber, runs in background task
│   │   └── handlers.py        # per-channel message handlers
│   ├── ws/
│   │   └── hub.py             # in-memory WS connection hub
│   ├── migrations/            # Alembic versions
│   └── seed.py                # python -m app.seed
└── tests/
    ├── conftest.py
    ├── test_auth.py
    ├── test_alarms.py
    └── test_telemetry.py
```

## Local development

```bash
# from repo root
cp .env.example .env
docker compose up -d postgres mosquitto
cd backend
python -m venv .venv && .venv/Scripts/activate    # PowerShell: .venv\Scripts\Activate.ps1
pip install -e .[dev]
alembic upgrade head
python -m app.seed
uvicorn app.main:app --reload --port 8000
```

OpenAPI docs: <http://localhost:8000/docs>.

## Configuration

All settings via env vars (see `.env.example`). The `Settings` class must:

- Fail fast on missing required vars.
- Reject `JWT_SECRET` shorter than 32 characters.
- Parse `CORS_ORIGINS` as a comma-separated list.

## Auth implementation notes

- Password hashing: `bcrypt` via passlib.
- JWT: HS256, expiry from `JWT_EXPIRE_MINUTES`.
- `require_role(*roles)` is a dependency factory:
  ```python
  @router.post("/alarms/{id}/resolve")
  async def resolve_alarm(id: UUID, user = Depends(require_role("engineer","manager","admin"))):
      ...
  ```
- Failed logins write `auth.login_failed` to `audit_log` with the attempted email.

## MQTT subscriber notes

- Runs as an asyncio task started in the FastAPI `lifespan` context.
- Uses a bounded `asyncio.Queue` between paho callback and the async writer to avoid blocking the network thread.
- Validates payloads with the Pydantic schemas in `app/schemas/mqtt.py`.
- Inserts telemetry in batches (e.g. every 500 ms or 200 rows) for throughput.
- On asset status changes, writes to `asset_status_history` and rebroadcasts via the WS hub.

## WS hub notes

- In-memory `dict[asset_id, set[WebSocket]]` plus a `dict[site_id, set[WebSocket]]`.
- One async lock per map; broadcasts iterate a snapshot of the set.
- On send failure, the connection is removed.
- `TODO(future): swap for Redis pub/sub when scaling beyond one process.`

## Testing

- Unit tests for services (no FastAPI client).
- Integration tests with `httpx.AsyncClient` against the app + a test Postgres (use `pytest-postgresql` or a docker compose `postgres-test` profile).
- Alarm state machine and `require_role` should be covered.

## Definition of done

See `docs/AGENT_WORKFLOW.md` § Definition of done. In particular:

- All endpoints in `docs/API_CONTRACT.md` return correct shapes and status codes.
- `python -m app.seed` produces the seed described in `docs/DATA_MODEL.md`.
- WS clients receive telemetry within ~1s of MQTT publish.
- No `TODO(backend)` markers remain.

## Things explicitly out of scope (leave as `TODO(future)`)

- Refresh tokens, password reset flows
- Redis-backed WS hub
- Prometheus `/metrics`
- Multi-company tenant isolation beyond the `company_id` filter
- Dead-letter queue for malformed MQTT messages
