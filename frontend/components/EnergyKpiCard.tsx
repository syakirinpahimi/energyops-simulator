import clsx from "clsx";
import { fmtKwh, fmtNumber } from "@/lib/format";

interface Props {
  label: string;
  energyKwh: number;
  deltaPct?: number;
  costEstimate?: number;
  unit?: string;
  className?: string;
}

export function EnergyKpiCard({ label, energyKwh, deltaPct, costEstimate, unit, className }: Props) {
  const trendColor =
    deltaPct === undefined
      ? "text-steel-400"
      : deltaPct > 0
        ? "text-signal-warn"
        : "text-signal-run";
  const arrow = deltaPct === undefined ? "·" : deltaPct >= 0 ? "▲" : "▼";

  return (
    <div
      className={clsx(
        "flex flex-col gap-2 rounded-md border border-steel-700 bg-steel-800 p-4 shadow-panel",
        className
      )}
    >
      <div className="text-xs uppercase tracking-wider text-steel-300">{label}</div>
      <div className="font-mono text-3xl text-steel-50 tabular-nums">
        {unit === "kWh" || unit === undefined ? fmtKwh(energyKwh) : `${fmtNumber(energyKwh, 1)} ${unit}`}
      </div>
      <div className="flex items-center justify-between text-xs">
        {deltaPct !== undefined ? (
          <span className={clsx("font-medium", trendColor)}>
            {arrow} {fmtNumber(Math.abs(deltaPct), 1)}% vs prev
          </span>
        ) : (
          <span className="text-steel-500">—</span>
        )}
        {costEstimate !== undefined && (
          <span className="text-steel-400">≈ MYR {fmtNumber(costEstimate, 0)}</span>
        )}
      </div>
    </div>
  );
}
