# Contract change requests

This file tracks proposed deviations from the frozen contract docs
(`API_CONTRACT.md`, `DATA_MODEL.md`). Each entry is opened by a track that
hits a divergence and waits for the architect track to either accept the
change (and patch the frozen docs) or reject it (and require the track to
realign).

## Open

### CC-001 - MQTT topic shape (simulator <-> backend agreement)

**Opened by:** simulator track, 2026-05-27

**Frozen contract** (`API_CONTRACT.md` § MQTT topic conventions):

```
energyops/<company_slug>/<site_slug>/<area_slug>/<asset_slug>/<channel>
```

Six segments. `<channel>` is `telemetry | status | alarm | heartbeat`. The
backend would subscribe to `energyops/+/+/+/+/+`.

**Brief in this session** asked for:

```
industrial/{site_slug}/{area_slug}/{asset_slug}/{sensor_slug}
```

Five segments. No company segment. The sensor slug is a topic level
instead of a payload field.

**What the simulator + new MQTT consumer ship today**

- Telemetry: `industrial/{site}/{area}/{asset}/{sensor}` (matches the brief).
- Status:    `industrial/{site}/{area}/{asset}/_status`
- Heartbeat: `industrial/{site}/{area}/{asset}/_heartbeat`

The reserved `_status` / `_heartbeat` slots reuse the sensor segment so a
single five-segment wildcard subscription (`industrial/+/+/+/+`) catches
everything. The backend `mqtt_consumer.py` matches this layout exactly.

**Impact per track**

| Track     | Affected files                                      | Effort to realign with frozen docs                            |
|-----------|-----------------------------------------------------|---------------------------------------------------------------|
| simulator | `simulator/assets.py` (`topic_for`, `asset_channel_topic`), `simulator/config.py` | small -- two helpers and a default                            |
| backend   | `backend/app/services/mqtt_consumer.py` (`TOPIC_FILTER`, `parse_topic`) | small -- adjust segment count and channel parsing             |
| frontend  | none today (no direct MQTT consumer)                | none                                                          |

**Migration plan (one-line)**

Pick the canonical layout in this file, then in one PR update the helpers
in both tracks and the backend `TOPIC_FILTER`. Tests in `tests/simulator/`
will catch any miss.

**Recommendation**

Adopt the brief's five-segment layout (`industrial/...`) in
`API_CONTRACT.md`. Rationale: the company is implicit for a single-tenant
MVP, the sensor-as-segment lets dashboards subscribe to one metric across
all assets cheaply, and the `_status`/`_heartbeat` reservation avoids a
sixth segment without losing channel semantics. If multi-tenancy becomes
real, prepend `{company_slug}` and bump the wildcard.

**Status:** awaiting architect decision.
