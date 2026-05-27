# Agent Workflow

How multiple agent sessions (or developers) work on this repo in parallel without colliding. Read before opening a new session.

## Principles

1. **One owner per file.** Every file has a single owning track. Other tracks may *read* it but must not *write* it without coordination.
2. **Contracts are frozen.** `docs/API_CONTRACT.md` and `docs/DATA_MODEL.md` are the wire boundary. Any change there is a contract change and must be agreed across tracks.
3. **No placeholder code that pretends to work.** A function either works or is left as `raise NotImplementedError("TODO(track-X): ...")`. Frontend stubs render `TODO` placeholders, never fake data that looks real.
4. **TODOs are tagged.** Use `TODO(track-name)` so search reveals who owns the gap. Examples: `TODO(backend)`, `TODO(frontend)`, `TODO(simulator)`, `TODO(infra)`, `TODO(future)`.
5. **Small commits.** One logical change per commit. Commit message prefix matches the track: `backend:`, `frontend:`, `simulator:`, `infra:`, `docs:`.

## Tracks

The work is split into five tracks. Each can be picked up in its own agent session.

| Track       | Owns                                                | Reads (must not edit)                          |
|-------------|-----------------------------------------------------|------------------------------------------------|
| `architect` | `README.md`, `docs/**`, `docker-compose.yml`, `.env.example`, `.gitignore` | nothing                                        |
| `backend`   | `backend/**`, `infra/postgres/**`                   | `docs/**`                                      |
| `frontend`  | `frontend/**`                                       | `docs/**`, `backend/app/schemas/**` (read-only types) |
| `simulator` | `simulator/**`                                      | `docs/**`                                      |
| `infra`     | `infra/mosquitto/**`, CI workflows under `.github/` | `docker-compose.yml` (edits require architect handshake) |

## File ownership map

```
README.md                       architect
.env.example                    architect
.gitignore                      architect
docker-compose.yml              architect (infra may propose patches via PR)
docs/ARCHITECTURE.md            architect
docs/API_CONTRACT.md            architect (frozen; change = contract bump)
docs/DATA_MODEL.md              architect (frozen; change = contract bump)
docs/AGENT_WORKFLOW.md          architect

backend/                        backend
backend/README.md               backend
backend/Dockerfile              backend
backend/pyproject.toml          backend
backend/app/**                  backend
backend/tests/**                backend
infra/postgres/init.sql         backend
infra/postgres/migrations/**    backend

frontend/                       frontend
frontend/README.md              frontend
frontend/Dockerfile             frontend
frontend/package.json           frontend
frontend/app/**                 frontend
frontend/components/**          frontend
frontend/lib/**                 frontend

simulator/                      simulator
simulator/README.md             simulator
simulator/Dockerfile            simulator
simulator/pyproject.toml        simulator
simulator/app/**                simulator

infra/mosquitto/**              infra
.github/workflows/**            infra
```

If you need to touch a file outside your track, stop and post a handoff note in your final message rather than editing it.

## Track contracts (the "what to build" per session)

### Track: backend

**Goal:** implement `backend/` so REST + WS contracts in `docs/API_CONTRACT.md` work end-to-end.

Suggested order:

1. Project skeleton: `pyproject.toml`, `app/main.py`, `app/config.py`, `Dockerfile`.
2. Database: SQLAlchemy models matching `docs/DATA_MODEL.md`, Alembic baseline migration.
3. Auth: `POST /auth/login`, `GET /auth/me`, JWT issuance + `require_role` dependency.
4. Hierarchy CRUD endpoints.
5. Telemetry history endpoint backed by Timescale continuous aggregates.
6. Alarms endpoints + audit log writer.
7. WS hub at `/ws/telemetry`.
8. MQTT subscriber (background task) writing to telemetry + republishing to WS.
9. Reports (CSV first, PDF second).
10. Seed script `python -m app.seed`.

Tests live in `backend/tests/`. Aim for coverage of auth, alarm state machine, telemetry write path.

### Track: frontend

**Goal:** implement `frontend/` so a logged-in user can see live tiles, charts, alarms, and trigger reports.

Suggested order:

1. Next.js app skeleton, Tailwind, lint/format config.
2. Typed API client (`lib/api.ts`) generated from `docs/API_CONTRACT.md` shapes.
3. Auth: login page, JWT storage (httpOnly cookie preferred; localStorage acceptable for MVP), `useUser` hook.
4. App shell with role-aware nav.
5. Site ? area ? asset drill-down pages.
6. Asset detail page: status header, live metric tiles, Recharts time-series, alarm panel.
7. WS client `lib/ws.ts` with reconnect/backoff.
8. Alarms page with ack/resolve modals.
9. Reports page (request + download).
10. Audit log page (engineer+).

Until the backend is up, the frontend may use the typed client against a mocked fetch. **Do not** hardcode fake data that ships to production paths — gate mocks behind `NEXT_PUBLIC_USE_MOCKS=1`.

### Track: simulator

**Goal:** publish realistic telemetry/alarm/status messages to MQTT for all seeded assets.

Suggested order:

1. Project skeleton: `pyproject.toml`, `app/main.py`, `Dockerfile`.
2. Config loader: pull asset list from backend (`GET /api/v1/assets`) on startup; fall back to a local YAML if backend is unreachable.
3. Per-asset generator functions matching `DATA_MODEL.md` § Sensor template per asset type.
4. Tick loop: every `SIM_TICK_SECONDS`, publish one `telemetry` message per sensor.
5. Heartbeat every 30s on `…/heartbeat`.
6. Random fault injection at `SIM_FAULT_PROBABILITY`, publishing on `…/alarm`.
7. Status transitions when faults occur, published on `…/status`.

The simulator must respect MQTT topic conventions in `docs/API_CONTRACT.md` exactly. Any divergence is a contract bug, not a simulator change.

### Track: infra

**Goal:** make `docker compose up` produce a working broker and CI green.

1. `infra/mosquitto/mosquitto.conf` with anonymous off, password file, persistence on.
2. Optional `infra/mosquitto/passwd` generator script.
3. `.github/workflows/ci.yml`: backend lint+test, frontend lint+typecheck+build, simulator lint, docker build matrix.

### Track: architect (this track)

Owns the docs and skeleton. After the initial commit, the architect track only acts when:

- A contract needs to change (and another track has flagged it).
- A new cross-cutting concern appears (observability, auth refresh, multi-tenancy).
- A new track needs to be defined.

Architect changes are done via small, focused commits. Never rewrite a frozen doc — diff it.

## Session protocol

When a new agent session begins, do this in order:

1. Read `README.md`, `docs/ARCHITECTURE.md`, `docs/API_CONTRACT.md`, `docs/DATA_MODEL.md`, this file.
2. Identify which **track** you are working on. State it explicitly in your first message.
3. Touch only files your track owns. If you must read another track's files, do so with read tools — do not edit them.
4. Track progress with the todo tool.
5. Before finishing, leave a `STATUS.md` note **inside your track folder** (e.g. `backend/STATUS.md`) listing what works, what is stubbed, and what the next session in that track should pick up.

### `<track>/STATUS.md` template

```markdown
# <Track> status

Last updated: <ISO date>  by  <session id or name>

## Done
- ...

## In progress / partial
- ...

## TODO (next session)
- ...

## Open questions for the architect
- ...
```

## Contract change procedure

When a track discovers the contract needs to change (e.g. an endpoint shape is wrong, a missing field, a topic rename):

1. **Stop coding.** Do not silently diverge.
2. Open or extend `docs/CONTRACT_CHANGES.md` (architect creates it on first request) with:
   - the change you want
   - the impact on each track
   - a one-line migration plan
3. Wait for the architect track to merge the change into the frozen docs.
4. Resume work against the new contract.

## Definition of done (per track)

A track is "done" when:

- All endpoints/screens/topics in its section above are implemented per contract.
- Tests pass locally and in CI.
- `STATUS.md` is up to date with no open `TODO(track)` markers in the code (only `TODO(future)` permitted).
- `docker compose up` brings the service up cleanly with no errors in the first 60 seconds.

## TODO marker convention

Search the repo with `rg "TODO\("` to find every outstanding item.

| Marker            | Meaning                                                |
|-------------------|--------------------------------------------------------|
| `TODO(backend)`   | Backend track must address before its DoD              |
| `TODO(frontend)`  | Frontend track must address before its DoD             |
| `TODO(simulator)` | Simulator track must address                           |
| `TODO(infra)`     | Infra/CI track must address                            |
| `TODO(architect)` | Needs an architect decision (contract / cross-cutting) |
| `TODO(future)`    | Out of MVP scope, kept as a note                       |
| `FIXME`           | Known bug, fix before merging                          |

Plain `TODO` with no track tag is **not allowed** — it hides ownership.
