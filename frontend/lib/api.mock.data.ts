// Mock fallback layer.
// Activated only when NEXT_PUBLIC_USE_MOCKS === "1".
// Provides deterministic data so the UI can be exercised before
// the backend track is online. NEVER ships real data through here.

import type {
  Alarm,
  Area,
  Asset,
  AuditEntry,
  Company,
  ReportSummary,
  Sensor,
  Site,
  User
} from "./types";

export function isMockEnabled(): boolean {
  if (typeof process === "undefined") return false;
  return process.env.NEXT_PUBLIC_USE_MOCKS === "1";
}

// ---------- seed data ----------

const COMPANY: Company = { id: "c-1", name: "Acme Industrial", slug: "acme" };

const SITES: Site[] = [
  {
    id: "s-kuantan",
    company_id: "c-1",
    name: "Kuantan Plant",
    slug: "kuantan-plant",
    timezone: "Asia/Kuala_Lumpur",
    created_at: "2026-01-15T08:00:00Z"
  },
  {
    id: "s-johor",
    company_id: "c-1",
    name: "Johor Solar Farm",
    slug: "johor-solar",
    timezone: "Asia/Kuala_Lumpur",
    created_at: "2026-01-15T08:00:00Z"
  },
  {
    id: "s-kl",
    company_id: "c-1",
    name: "KL Data Centre",
    slug: "kl-data-centre",
    timezone: "Asia/Kuala_Lumpur",
    created_at: "2026-01-15T08:00:00Z"
  }
];

const AREAS: Area[] = [
  { id: "a-kuantan-boiler", site_id: "s-kuantan", name: "Boiler Hall", slug: "boiler-hall" },
  { id: "a-kuantan-pumps", site_id: "s-kuantan", name: "Pump Station", slug: "pump-station" },
  { id: "a-johor-row-a", site_id: "s-johor", name: "Inverter Row A", slug: "inverter-row-a" },
  { id: "a-johor-row-b", site_id: "s-johor", name: "Inverter Row B", slug: "inverter-row-b" },
  { id: "a-kl-cooling", site_id: "s-kl", name: "Cooling", slug: "cooling" },
  { id: "a-kl-power", site_id: "s-kl", name: "Power Distribution", slug: "power" }
];

function asset(
  id: string,
  area_id: string,
  name: string,
  asset_type: string,
  status: Asset["status"],
  rated_power_kw: number,
  metadata: Record<string, unknown> = {}
): Asset {
  return {
    id,
    area_id,
    slug: id,
    name,
    asset_type,
    status,
    rated_power_kw,
    metadata,
    created_at: "2026-01-15T08:00:00Z"
  };
}

const ASSETS: Asset[] = [
  asset("asset-boiler-2", "a-kuantan-boiler", "Boiler #2", "boiler", "online", 350, { model: "ACME-B200" }),
  asset("asset-pump-p101", "a-kuantan-pumps", "Pump P-101", "pump", "fault", 75, { model: "ACME-P75" }),
  asset("asset-pump-p102", "a-kuantan-pumps", "Pump P-102", "pump", "online", 75),
  asset("asset-inv-a04", "a-johor-row-a", "Inverter A-04", "inverter", "online", 250),
  asset("asset-inv-b07", "a-johor-row-b", "Inverter B-07", "inverter", "maintenance", 250),
  asset("asset-chiller-1", "a-kl-cooling", "Chiller 1", "chiller", "online", 420),
  asset("asset-chiller-2", "a-kl-cooling", "Chiller 2", "chiller", "offline", 420),
  asset("asset-ups-1", "a-kl-power", "UPS Bank 1", "ups", "online", 600)
];

const SENSORS_BY_ASSET: Record<string, Sensor[]> = {
  "asset-boiler-2": [
    { id: "snr-b2-pwr", asset_id: "asset-boiler-2", metric: "power_kw", unit: "kW" },
    { id: "snr-b2-tmp", asset_id: "asset-boiler-2", metric: "temperature_c", unit: "\u00B0C" },
    { id: "snr-b2-prs", asset_id: "asset-boiler-2", metric: "pressure_bar", unit: "bar" }
  ],
  "asset-pump-p101": [
    { id: "snr-p101-pwr", asset_id: "asset-pump-p101", metric: "power_kw", unit: "kW" },
    { id: "snr-p101-vib", asset_id: "asset-pump-p101", metric: "vibration_mm_s", unit: "mm/s" }
  ],
  "asset-pump-p102": [
    { id: "snr-p102-pwr", asset_id: "asset-pump-p102", metric: "power_kw", unit: "kW" },
    { id: "snr-p102-vib", asset_id: "asset-pump-p102", metric: "vibration_mm_s", unit: "mm/s" }
  ],
  "asset-inv-a04": [
    { id: "snr-a04-pwr", asset_id: "asset-inv-a04", metric: "power_kw", unit: "kW" },
    { id: "snr-a04-tmp", asset_id: "asset-inv-a04", metric: "temperature_c", unit: "\u00B0C" }
  ],
  "asset-inv-b07": [
    { id: "snr-b07-pwr", asset_id: "asset-inv-b07", metric: "power_kw", unit: "kW" }
  ],
  "asset-chiller-1": [
    { id: "snr-ch1-pwr", asset_id: "asset-chiller-1", metric: "power_kw", unit: "kW" },
    { id: "snr-ch1-tmp", asset_id: "asset-chiller-1", metric: "temperature_c", unit: "\u00B0C" }
  ],
  "asset-chiller-2": [
    { id: "snr-ch2-pwr", asset_id: "asset-chiller-2", metric: "power_kw", unit: "kW" }
  ],
  "asset-ups-1": [
    { id: "snr-ups1-pwr", asset_id: "asset-ups-1", metric: "power_kw", unit: "kW" }
  ]
};

function alarm(partial: Partial<Alarm> & Pick<Alarm, "id" | "asset_id" | "code" | "severity" | "message" | "state" | "opened_at">): Alarm {
  return {
    sensor_id: null,
    asset_name: null,
    sensor_name: null,
    triggered_value: null,
    threshold_value: null,
    acked_at: null,
    acked_by: null,
    acked_by_email: null,
    ack_note: null,
    resolved_at: null,
    resolved_by: null,
    resolved_by_email: null,
    resolve_note: null,
    ...partial
  };
}

const ALARMS: Alarm[] = [
  alarm({
    id: "alm-1",
    asset_id: "asset-pump-p101",
    asset_name: "Pump P-101",
    sensor_id: "snr-p101-vib",
    sensor_name: "vibration_mm_s",
    code: "VIBRATION_HIGH",
    severity: "critical",
    message: "Vibration exceeded 11.2 mm/s on Pump P-101",
    state: "OPEN",
    triggered_value: 11.2,
    threshold_value: 8.0,
    opened_at: "2026-05-27T09:48:00Z"
  }),
  alarm({
    id: "alm-2",
    asset_id: "asset-chiller-2",
    asset_name: "Chiller 2",
    code: "OFFLINE",
    severity: "warning",
    message: "Chiller 2 has been offline for 18 minutes",
    state: "OPEN",
    opened_at: "2026-05-27T09:30:00Z"
  }),
  alarm({
    id: "alm-3",
    asset_id: "asset-boiler-2",
    asset_name: "Boiler #2",
    sensor_id: "snr-b2-tmp",
    sensor_name: "temperature_c",
    code: "TEMP_HIGH",
    severity: "warning",
    message: "Boiler #2 temperature drifted above 92 \u00B0C",
    state: "ACK",
    triggered_value: 92.4,
    threshold_value: 90.0,
    opened_at: "2026-05-27T08:11:00Z",
    acked_at: "2026-05-27T08:14:30Z",
    acked_by: "u-engineer",
    acked_by_email: "engineer@energyops.local",
    ack_note: "investigating sensor drift"
  })
];

function audit(
  id: string,
  ts: string,
  actor_email: string,
  action: string,
  target_type: string | null,
  target_id: string | null,
  metadata: Record<string, unknown> = {}
): AuditEntry {
  return { id, ts, actor_id: actor_email, actor_email, action, target_type, target_id, metadata };
}

const AUDIT: AuditEntry[] = [
  audit("aud-1", "2026-05-27T08:14:30Z", "engineer@energyops.local", "alarm.ack", "alarm", "alm-3", {
    note: "investigating sensor drift"
  }),
  audit("aud-2", "2026-05-27T07:55:00Z", "operator@energyops.local", "auth.login", "user", "u-operator")
];

const REPORTS: ReportSummary[] = [
  {
    id: "rpt-1",
    kind: "energy",
    format: "pdf",
    status: "ready",
    params: { site_id: "s-kuantan", from: "2026-05-01", to: "2026-05-26" },
    file_size_bytes: 184320,
    created_by: "u-manager",
    created_at: "2026-05-26T18:02:00Z"
  }
];

const USERS: User[] = [
  { id: "u-admin", email: "admin@energyops.local", name: "Admin", role: "admin", company_id: "c-1", created_at: "2026-01-15T08:00:00Z" },
  { id: "u-manager", email: "manager@energyops.local", name: "Manager", role: "manager", company_id: "c-1", created_at: "2026-01-15T08:00:00Z" },
  { id: "u-engineer", email: "engineer@energyops.local", name: "Engineer", role: "engineer", company_id: "c-1", created_at: "2026-01-15T08:00:00Z" },
  { id: "u-operator", email: "operator@energyops.local", name: "Operator", role: "operator", company_id: "c-1", created_at: "2026-01-15T08:00:00Z" }
];

export const MOCK_DATA = { COMPANY, SITES, AREAS, ASSETS, SENSORS_BY_ASSET, ALARMS, AUDIT, REPORTS, USERS };
