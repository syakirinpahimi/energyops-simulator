// Mock fetch handler. Routes paths to in-memory data and simulates a tiny
// network delay so loading states are visible. Telemetry returns a
// deterministic-but-jittered series so charts look alive.

import { MOCK_DATA } from "./api.mock.data";
import type {
  Alarm,
  Asset,
  AssetSnapshot,
  AuditEntry,
  LoginResponse,
  Paginated,
  ReportSummary,
  TelemetrySeries,
  User
} from "./types";

export { isMockEnabled } from "./api.mock.data";

interface MockOpts {
  method?: "GET" | "POST" | "PATCH" | "DELETE";
  body?: unknown;
  query?: Record<string, string | number | undefined | null>;
}

const wait = (ms = 80) => new Promise((r) => setTimeout(r, ms));

function jitterSeries(seed: number, len: number, base: number, amp: number) {
  const out: { ts: string; value: number }[] = [];
  const now = Date.now();
  for (let i = len - 1; i >= 0; i--) {
    const t = now - i * 60_000;
    const x = Math.sin((t / 60_000 + seed) * 0.4) * amp;
    const noise = ((Math.sin(t / 7000 + seed) + 1) / 2) * amp * 0.3;
    out.push({ ts: new Date(t).toISOString(), value: +(base + x + noise).toFixed(2) });
  }
  return out;
}

function findUser(email: string): User | undefined {
  return MOCK_DATA.USERS.find((u) => u.email.toLowerCase() === email.toLowerCase());
}

export async function mockFetch<T>(path: string, opts: MockOpts = {}): Promise<T> {
  await wait();
  const url = new URL(path, "http://mock.local");
  const p = url.pathname;
  const q = opts.query ?? Object.fromEntries(url.searchParams);
  const method = opts.method ?? "GET";

  // ---- Auth ----
  if (p === "/api/v1/auth/login" && method === "POST") {
    const body = opts.body as { email?: string };
    const u = findUser(body?.email ?? "");
    if (!u) throw mkError(401, "INVALID_CREDENTIALS", "Unknown user");
    const resp: LoginResponse = {
      access_token: `mock.${u.role}.${u.id}`,
      token_type: "bearer",
      user: u
    };
    return resp as unknown as T;
  }

  if (p === "/api/v1/auth/me") {
    return MOCK_DATA.USERS[3] as unknown as T; // operator default
  }

  // ---- Hierarchy ----
  if (p === "/api/v1/companies") return MOCK_DATA.COMPANY as unknown as T; // single tenant for MVP
  if (p === "/api/v1/sites") return MOCK_DATA.SITES as unknown as T;
  if (p === "/api/v1/areas") {
    const sid = q.site_id as string | undefined;
    return (sid ? MOCK_DATA.AREAS.filter((a) => a.site_id === sid) : MOCK_DATA.AREAS) as unknown as T;
  }
  if (p === "/api/v1/assets") {
    const aid = q.area_id as string | undefined;
    const sid = q.site_id as string | undefined;
    let assets: Asset[] = MOCK_DATA.ASSETS;
    if (aid) assets = assets.filter((a) => a.area_id === aid);
    if (sid) {
      const areaIds = MOCK_DATA.AREAS.filter((ar) => ar.site_id === sid).map((ar) => ar.id);
      assets = assets.filter((a) => areaIds.includes(a.area_id));
    }
    return assets as unknown as T;
  }

  // /api/v1/assets/{id}, /sensors, /snapshot
  const assetMatch = p.match(/^\/api\/v1\/assets\/([^/]+)(\/(sensors|snapshot))?$/);
  if (assetMatch) {
    const id = assetMatch[1];
    const sub = assetMatch[3];
    const asset = MOCK_DATA.ASSETS.find((a) => a.id === id);
    if (!asset) throw mkError(404, "ASSET_NOT_FOUND", "Unknown asset");
    if (!sub) return asset as unknown as T;
    if (sub === "sensors") return (MOCK_DATA.SENSORS_BY_ASSET[id] ?? []) as unknown as T;
    if (sub === "snapshot") {
      const sensors = MOCK_DATA.SENSORS_BY_ASSET[id] ?? [];
      const metrics: AssetSnapshot["metrics"] = {};
      for (const s of sensors) {
        const seriesSeed = id.length + s.metric.length;
        const last = jitterSeries(seriesSeed, 1, baseFor(s.metric), 5)[0];
        metrics[s.metric] = { value: last.value, ts: last.ts };
      }
      const snap: AssetSnapshot = {
        asset_id: id,
        status: asset.status,
        last_seen: new Date().toISOString(),
        metrics,
        open_alarms: MOCK_DATA.ALARMS.filter((a) => a.asset_id === id && a.state === "OPEN").length
      };
      return snap as unknown as T;
    }
  }

  // ---- Telemetry history ----
  if (p === "/api/v1/telemetry") {
    const assetId = q.asset_id as string;
    const metric = (q.metric as string) ?? "power_kw";
    const seed = (assetId?.length ?? 1) + metric.length;
    const series: TelemetrySeries = {
      asset_id: assetId,
      metric,
      bucket: (q.bucket as string) ?? "1m",
      agg: (q.agg as string) ?? "avg",
      points: jitterSeries(seed, 60, baseFor(metric), 8)
    };
    return series as unknown as T;
  }

  // ---- Alarms ----
  if (p === "/api/v1/alarms" && method === "GET") {
    const state = q.state as string | undefined;
    const items = MOCK_DATA.ALARMS.filter((a) => (state ? a.state === state : true));
    const resp: Paginated<Alarm> = { items, next_cursor: null };
    return resp as unknown as T;
  }
  const alarmAck = p.match(/^\/api\/v1\/alarms\/([^/]+)\/ack$/);
  if (alarmAck && method === "POST") {
    const id = alarmAck[1];
    const a = MOCK_DATA.ALARMS.find((x) => x.id === id);
    if (!a) throw mkError(404, "ALARM_NOT_FOUND", "Unknown alarm");
    if (a.state !== "OPEN") throw mkError(409, "ALARM_STATE", "Alarm not OPEN");
    a.state = "ACK";
    a.acked_at = new Date().toISOString();
    a.acked_by = "u-operator";
    a.acked_by_email = "operator@energyops.local";
    a.ack_note = (opts.body as { note?: string })?.note ?? null;
    MOCK_DATA.AUDIT.unshift({
      id: `aud-${Date.now()}`,
      ts: a.acked_at,
      actor_id: "u-operator",
      actor_email: "operator@energyops.local",
      action: "alarm.ack",
      target_type: "alarm",
      target_id: a.id,
      metadata: { note: a.ack_note ?? "" }
    });
    return a as unknown as T;
  }
  const alarmRes = p.match(/^\/api\/v1\/alarms\/([^/]+)\/resolve$/);
  if (alarmRes && method === "POST") {
    const id = alarmRes[1];
    const a = MOCK_DATA.ALARMS.find((x) => x.id === id);
    if (!a) throw mkError(404, "ALARM_NOT_FOUND", "Unknown alarm");
    a.state = "RESOLVED";
    a.resolved_at = new Date().toISOString();
    a.resolved_by = "u-engineer";
    a.resolved_by_email = "engineer@energyops.local";
    a.resolve_note = (opts.body as { note?: string })?.note ?? null;
    MOCK_DATA.AUDIT.unshift({
      id: `aud-${Date.now()}`,
      ts: a.resolved_at,
      actor_id: "u-engineer",
      actor_email: "engineer@energyops.local",
      action: "alarm.resolve",
      target_type: "alarm",
      target_id: a.id,
      metadata: { note: a.resolve_note ?? "" }
    });
    return a as unknown as T;
  }

  // ---- Audit ----
  if (p === "/api/v1/audit") {
    const resp: Paginated<AuditEntry> = { items: MOCK_DATA.AUDIT, next_cursor: null };
    return resp as unknown as T;
  }

  // ---- Reports ----
  if (p === "/api/v1/reports/energy" && method === "POST") {
    const r: ReportSummary = {
      id: `rpt-${Date.now()}`,
      kind: "energy",
      format: ((opts.body as { format?: "pdf" | "csv" })?.format ?? "pdf"),
      status: "ready",
      params: (opts.body as Record<string, unknown>) ?? {},
      file_size_bytes: 102400,
      created_by: "u-manager",
      created_at: new Date().toISOString()
    };
    MOCK_DATA.REPORTS.unshift(r);
    MOCK_DATA.AUDIT.unshift({
      id: `aud-${Date.now()}`,
      ts: r.created_at,
      actor_id: "u-manager",
      actor_email: "manager@energyops.local",
      action: "report.create",
      target_type: "report",
      target_id: r.id,
      metadata: {}
    });
    return r as unknown as T;
  }
  if (p === "/api/v1/reports") return MOCK_DATA.REPORTS as unknown as T;

  // ---- Users (admin) ----
  if (p === "/api/v1/users") return MOCK_DATA.USERS as unknown as T;

  throw mkError(404, "MOCK_NOT_FOUND", `No mock handler for ${method} ${p}`);
}

function baseFor(metric: string): number {
  switch (metric) {
    case "power_kw":
      return 220;
    case "temperature_c":
      return 68;
    case "pressure_bar":
      return 4.2;
    case "vibration_mm_s":
      return 6.5;
    case "energy_kwh":
      return 1450;
    default:
      return 50;
  }
}

class MockApiError extends Error {
  status: number;
  code: string;
  constructor(status: number, code: string, msg: string) {
    super(msg);
    this.status = status;
    this.code = code;
  }
}

function mkError(status: number, code: string, msg: string) {
  return new MockApiError(status, code, msg);
}
