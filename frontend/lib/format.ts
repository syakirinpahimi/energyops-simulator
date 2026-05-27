import type { Asset, UiAssetState } from "./types";

export function fmtNumber(n: number | undefined | null, digits = 1): string {
  if (n === null || n === undefined || Number.isNaN(n)) return "—";
  return n.toLocaleString(undefined, {
    minimumFractionDigits: digits,
    maximumFractionDigits: digits
  });
}

export function fmtKw(n: number | undefined | null): string {
  return `${fmtNumber(n, 1)} kW`;
}

export function fmtKwh(n: number | undefined | null): string {
  return `${fmtNumber(n, 0)} kWh`;
}

export function fmtRelativeTime(iso: string | undefined | null): string {
  if (!iso) return "—";
  const t = new Date(iso).getTime();
  if (Number.isNaN(t)) return "—";
  const diff = Date.now() - t;
  const s = Math.round(diff / 1000);
  if (s < 5) return "just now";
  if (s < 60) return `${s}s ago`;
  const m = Math.round(s / 60);
  if (m < 60) return `${m}m ago`;
  const h = Math.round(m / 60);
  if (h < 24) return `${h}h ago`;
  const d = Math.round(h / 24);
  return `${d}d ago`;
}

export function fmtClock(iso: string | undefined | null): string {
  if (!iso) return "—";
  const d = new Date(iso);
  if (Number.isNaN(d.getTime())) return "—";
  return d.toLocaleTimeString(undefined, {
    hour: "2-digit",
    minute: "2-digit",
    second: "2-digit",
    hour12: false
  });
}

// SCADA-style label per UI state.
export function uiStateLabel(s: UiAssetState): string {
  switch (s) {
    case "running":
      return "Running";
    case "warning":
      return "Warning";
    case "fault":
      return "Fault";
    case "offline":
      return "Offline";
    default:
      return "Unknown";
  }
}

export function assetTypeLabel(t: Asset["asset_type"]): string {
  return t.charAt(0).toUpperCase() + t.slice(1);
}
