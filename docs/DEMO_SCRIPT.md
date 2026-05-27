# Demo script

A five-minute walkthrough that hits the three personas a recruiter cares
about: an operator catching a fault, a manager exporting a report, and an
admin looking at the audit trail.

Total time: ~5 minutes. Stack must already be running
(`docker compose up --build` and `make seed`).

---

## 0. Pre-flight (30 seconds)

Confirm the stack is healthy:

```bash
docker compose ps
curl -s http://localhost:8000/health | jq
```

You should see five running services and `{"status":"ok","db":"up",...}`.

If the alarms list is empty, run the seed once:

```bash
make seed
```

The seed creates one OPEN `VIBRATION_HIGH` alarm on `Pump P-101`. The
simulator will keep producing live readings around that pump every five
seconds.

---

## 1. Operator: detect the pump anomaly (90 seconds)

1. Open http://localhost:3000.
2. Log in:
   - email: `operator@energyops.local`
   - password: `Operator#12345`
3. Land on **Dashboard**. Note the alarm banner at the top:
   `1 OPEN alarm - Pump P-101 - Bearing vibration above warning
   threshold`.
4. Click **Pump P-101** in the asset tree (sidebar, under
   `Kuantan Plant -> Utilities`).
5. The asset detail page shows live KPIs and a vibration trend chart.
   Vibration should be hovering around 8 mm/s with an occasional spike.
   The badge in the header reads `FAULT`.

Talking points:
- The data is streamed over WebSocket (`/ws/telemetry`), not polled.
- The alarm was opened by the seed, but the rule that opens it lives in
  `backend/app/services/alarm_engine.py`. The simulator deliberately
  drives vibration over the 8 mm/s threshold.

## 2. Operator: acknowledge the alarm (60 seconds)

1. Click **Alarms** in the top nav.
2. The single OPEN row is highlighted. Click it.
3. In the side panel, type a note: `investigating bearing` and click
   **Acknowledge**.
4. The state badge flips from `OPEN` to `ACK`. The row collapses out of
   the OPEN filter.

Talking points:
- The ack call is `POST /api/v1/alarms/{id}/acknowledge`. The backend
  writes an `audit_log` row in the same transaction via
  `services/audit.write_audit(...)`.
- The action is gated by `require_role("operator", "engineer",
  "manager", "admin")` - a single FastAPI dependency, not scattered
  per-handler checks.

## 3. Manager: export the energy report (90 seconds)

1. Sign out. Sign in as `manager@energyops.local` /
   `Manager#12345`.
2. Open **Reports**.
3. Pick:
   - site: `Kuantan Plant`
   - range: last 24 hours
   - format: `PDF`
4. Click **Generate**. The PDF downloads. It contains the title,
   site, range, total kWh, peak kW, top consumers, and an alarm
   summary.
5. Click **Generate** again with format `CSV`. Same payload, row per
   reading.

Talking points:
- Reports are manager+ via the same role dependency.
- Files are written to `./reports/` on the host (volume mounted) so
  they survive container restarts and can be re-served.
- PDF rendering uses `reportlab`; CSV uses the stdlib. No external
  service.

## 4. Admin (optional, 30 seconds)

1. Sign out. Sign in as `admin@energyops.local` / `Admin#12345`.
2. Open **Audit log**.
3. The `alarm.ack` and `report.create` entries are at the top, with
   actor email, timestamp, and the ack note in the metadata column.

Talking points:
- The audit table uses the user-prompt column names (`timestamp`,
  `user_id`, `entity_type`, `entity_id`, `details_json`) and is mapped
  to the contract names (`ts`, `actor_id`, `target_type`, `target_id`,
  `metadata`) via a single Pydantic schema mapper.

---

## Reset between demos

```bash
make reset-db   # drops everything, re-runs migrations + seed
```

That brings the OPEN pump alarm back, clears any acknowledgements, and
gives the next viewer a clean slate.
