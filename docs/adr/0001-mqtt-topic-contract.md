# ADR 0001: MQTT topic contract

- **Status:** Accepted
- **Date:** 2026-05-27
- **Deciders:** architect track (with input from simulator + backend tracks)
- **Supersedes:** the six-segment `energyops/<company>/...` shape originally
  drafted in `docs/API_CONTRACT.md` § MQTT topic conventions, and the
  pending change request previously tracked in `docs/CONTRACT_CHANGES.md`
  (CC-001).

## Context

Two MQTT topic shapes were in flight at the same time:

1. **Original contract (`docs/API_CONTRACT.md`):** six segments,
   `energyops/<company_slug>/<site_slug>/<area_slug>/<asset_slug>/<channel>`,
   with `<channel>` ∈ `telemetry | status | alarm | heartbeat`.
2. **Brief / implementation:** five segments,
   `industrial/{site_slug}/{area_slug}/{asset_slug}/{sensor_slug}`,
   with `_status` / `_heartbeat` reusing the sensor slot.

The simulator (`simulator/assets.py`, `simulator/config.py`,
`simulator/main.py`) and the backend MQTT consumer
(`backend/app/services/mqtt_consumer.py`) both ship the five-segment
shape today. The contract document still described the six-segment
shape, which produced a real divergence between docs and code.

This ADR picks one shape and aligns the docs to it.

## Decision

**Adopt the five-segment shape for MVP:**

```
industrial/{site_slug}/{area_slug}/{asset_slug}/{sensor_slug}
```

Reserved per-asset channels reuse the sensor slot with an underscore
prefix so a single five-segment wildcard subscription matches
everything:

```
industrial/{site_slug}/{area_slug}/{asset_slug}/_status
industrial/{site_slug}/{area_slug}/{asset_slug}/_heartbeat
```

The backend subscription filter is `industrial/+/+/+/+`. QoS is `1`
across the board. Telemetry is `retain=false`; the latest `_status` is
`retain=true` so new subscribers see current state.

Per-message context that used to live in topic segments (company,
channel) lives in the JSON payload instead. The telemetry payload
already carries `company`, `site`, `area`, `asset`, `sensor`, `metric`,
`value`, `unit`, `quality`, and `anomaly`.

## Rationale

- **Already shipping.** Both simulator and backend consumer use this
  shape. Realigning to the six-segment form would require coordinated
  changes to working code with no behavioural payoff for the MVP.
- **Single tenant for now.** EnergyOps is a single-tenant demo; the
  company segment was effectively a constant. Putting it in the
  payload (where it's already present) keeps the topic tree compact.
- **Per-metric subscriptions are cheap.** Promoting `sensor_slug` to a
  topic level lets a future dashboard subscribe to one metric across
  every asset (`industrial/+/+/+/power_kw`) without parsing payloads.
- **Channel reservation is enough.** Using `_status` / `_heartbeat` in
  the sensor slot is a small, explicit convention that keeps the
  five-segment wildcard universal and avoids a sixth segment whose
  cardinality is tiny.
- **Reversible.** Multi-tenancy can prepend `{company_slug}` later by
  bumping `TOPIC_FILTER` and the simulator's topic builder; nothing in
  the payload schema needs to change.

## Consequences

### Positive

- Docs and code now agree. New contributors can read
  `docs/API_CONTRACT.md` and trust it.
- The simulator and the backend consumer continue to work without
  modification.
- A single subscription filter (`industrial/+/+/+/+`) covers
  telemetry, status, and heartbeat traffic.

### Negative

- Multi-tenant deployments will eventually need a sixth segment.
  Mitigation: add a `{company_slug}` prefix and bump the filter; this
  is a one-line change in both tracks plus a versioned contract bump.
- Operators cannot tell `_status` from `_heartbeat` from a single
  wildcard at a glance; they have to inspect the sensor slot.

### Neutral

- The contract change request previously tracked as **CC-001** in
  `docs/CONTRACT_CHANGES.md` is closed by this ADR. That file is no
  longer the source of truth for this divergence.

## Affected components

| Track     | File(s)                                                                                  | Change                                |
|-----------|------------------------------------------------------------------------------------------|---------------------------------------|
| docs      | `docs/API_CONTRACT.md`                                                                   | rewrite the MQTT section to match     |
| docs      | `docs/ARCHITECTURE.md`                                                                   | reference the new section verbatim    |
| docs      | `README.md`                                                                              | drop the divergence note              |
| docs      | `docs/CONTRACT_CHANGES.md`                                                               | mark CC-001 as resolved → see this ADR |
| simulator | `simulator/config.py`, `simulator/README.md`, `simulator/STATUS.md`, `simulator/assets.py` | drop `energyops/` references          |
| backend   | `backend/STATUS.md`, `backend/app/services/mqtt_consumer.py`                             | comments only — code already correct  |

## Validation

The backend MQTT consumer enforces the chosen shape at parse time:

1. `parse_topic` rejects topics that do not have exactly five segments.
2. `parse_message` rejects samples whose `timestamp` is more than five
   minutes in the future.
3. `quality == "bad"` readings are dropped from telemetry inserts but
   logged.
4. Inserts are idempotent on `(asset_id, sensor_id, ts)`.

`tests/simulator/test_topics.py` and `tests/simulator/test_mqtt_parsing.py`
pin the topic strings produced by the simulator and the parser used by
the backend. Any future drift will fail those tests.
