/**
 * Type mirrors of the backend responses we consume on the reports/alarms/
 * audit pages. Keep aligned with ``backend/app/schemas.py``; this is the
 * "manual zod mirror" approach noted in ``frontend/README.md``.
 */

export type Role = "operator" | "engineer" | "manager" | "admin";

export interface User {
  id: string;
  email: string;
  name: string;
  role: Role;
  company_id: string;
  created_at: string;
}

export interface LoginResponse {
  access_token: string;
  token_type: "bearer";
  user: User;
}

export type AlarmSeverity = "info" | "warning" | "critical";
export type AlarmState = "OPEN" | "ACK" | "RESOLVED";

export interface Alarm {
  id: string;
  asset_id: string;
  asset_name: string | null;
  sensor_id: string | null;
  sensor_name: string | null;
  code: string;
  severity: AlarmSeverity;
  message: string;
  state: AlarmState;
  triggered_value: number | null;
  threshold_value: number | null;
  opened_at: string;
  acked_at: string | null;
  acked_by: string | null;
  acked_by_email: string | null;
  ack_note: string | null;
  resolved_at: string | null;
  resolved_by: string | null;
  resolved_by_email: string | null;
  resolve_note: string | null;
}

export interface AlarmList {
  items: Alarm[];
  next_cursor: string | null;
}

export interface AuditEntry {
  id: string;
  ts: string;
  actor_id: string | null;
  actor_email: string;
  action: string;
  target_type: string | null;
  target_id: string | null;
  metadata: Record<string, unknown>;
}

export interface AuditList {
  items: AuditEntry[];
  next_cursor: string | null;
}

// Generic paginated envelope. Aligned with AlarmList/AuditList.
export interface Paginated<T> {
  items: T[];
  next_cursor: string | null;
}

export interface Company {
  id: string;
  name: string;
  slug: string;
}

export interface Site {
  id: string;
  company_id: string;
  slug: string;
  name: string;
  timezone: string;
  created_at: string;
}

export interface Area {
  id: string;
  site_id: string;
  slug: string;
  name: string;
}

export type AssetStatus = "online" | "offline" | "fault" | "maintenance";

// SCADA-friendly UI label mapping for AssetStatus.
export type UiAssetState = "running" | "warning" | "fault" | "offline";

export interface Asset {
  id: string;
  area_id: string;
  slug: string;
  name: string;
  asset_type: string;
  status: AssetStatus;
  rated_power_kw: number | null;
  metadata: Record<string, unknown>;
  created_at: string;
}

export interface Sensor {
  id: string;
  asset_id: string;
  metric: string;
  unit: string;
}

export interface TelemetryPoint {
  ts: string;
  value: number;
}

export interface TelemetrySeries {
  asset_id: string;
  metric: string;
  bucket: string;
  agg: string;
  points: TelemetryPoint[];
}

export interface AssetSnapshot {
  asset_id: string;
  status: AssetStatus;
  last_seen: string;
  metrics: Record<string, { value: number; ts: string }>;
  open_alarms: number;
}

export interface ReportTopAsset {
  asset_id: string;
  asset_name: string;
  energy_kwh: number;
  avg_power_kw: number;
  peak_kw: number;
}

export interface EnergySummary {
  from: string;
  to: string;
  duration_hours: number;
  asset_count: number;
  total_kwh: number;
  peak_kw: number;
  top_assets: ReportTopAsset[];
  alarms: { active: number; acknowledged: number; resolved: number; total: number };
  site: { id: string; name: string } | null;
  asset_id: string | null;
}

export interface ReportSummary {
  id: string;
  kind: "energy";
  format: "pdf" | "csv";
  status: "queued" | "ready" | "failed";
  params: Record<string, unknown>;
  file_size_bytes?: number;
  created_by: string;
  created_at: string;
}

// Backend uses online/offline/fault/maintenance; UI surfaces
// Running/Warning/Fault/Offline. We map "maintenance" -> Warning.
export function statusToUi(s: AssetStatus): UiAssetState {
  switch (s) {
    case "online":
      return "running";
    case "fault":
      return "fault";
    case "offline":
      return "offline";
    case "maintenance":
      return "warning";
    default:
      return "offline";
  }
}
