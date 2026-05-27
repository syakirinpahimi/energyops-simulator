# Contract change requests

This file tracks proposed deviations from the frozen contract docs
(`API_CONTRACT.md`, `DATA_MODEL.md`). Resolved entries are kept here as
a short audit trail; the full rationale moves to an ADR under
`docs/adr/`.

## Resolved

### CC-001 - MQTT topic shape (simulator <-> backend agreement)

**Opened by:** simulator track, 2026-05-27
**Resolved:** 2026-05-27 - see [`docs/adr/0001-mqtt-topic-contract.md`](adr/0001-mqtt-topic-contract.md).

The original `docs/API_CONTRACT.md` proposed a six-segment
`energyops/<company_slug>/<site_slug>/<area_slug>/<asset_slug>/<channel>`
shape. The simulator and backend MQTT consumer were already shipping a
five-segment `industrial/{site_slug}/{area_slug}/{asset_slug}/{sensor_slug}`
form (with `_status` / `_heartbeat` reserved in the sensor slot).

**Decision:** keep the five-segment `industrial/...` shape and align
the docs to it. Rationale, consequences, and validation rules live in
the ADR. `docs/API_CONTRACT.md` has been rewritten to match.

## Open

_None._
