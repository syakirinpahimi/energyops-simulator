import clsx from "clsx";
import type { Asset, UiAssetState } from "@/lib/types";
import { statusToUi } from "@/lib/types";
import { fmtKw, fmtRelativeTime } from "@/lib/format";
import { StatusChip, styleForState } from "./StatusBadge";

interface Props {
  asset: Asset;
  livePowerKw?: number;
  lastSeen?: string;
  openAlarms?: number;
  onClick?: () => void;
}

export function StatusCard({ asset, livePowerKw, lastSeen, openAlarms = 0, onClick }: Props) {
  const ui: UiAssetState = statusToUi(asset.status);
  const s = styleForState(ui);
  const rated = asset.rated_power_kw ?? 0;
  const utilisation =
    livePowerKw && rated > 0
      ? Math.min(100, Math.round((livePowerKw / rated) * 100))
      : 0;

  return (
    <button
      type="button"
      onClick={onClick}
      className={clsx(
        "group relative flex w-full flex-col gap-3 rounded-md border border-steel-700 bg-steel-800 p-4 text-left shadow-panel transition-colors",
        "hover:border-steel-500 focus:outline-none focus:ring-1 focus:ring-accent"
      )}
    >
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0">
          <div className="truncate font-semibold text-steel-50">{asset.name}</div>
          <div className="text-xs uppercase tracking-wider text-steel-300">
            {asset.asset_type}
          </div>
        </div>
        <StatusChip state={ui} />
      </div>

      <div className="flex items-end justify-between gap-3">
        <div>
          <div className="font-mono text-2xl text-steel-50 tabular-nums">
            {fmtKw(livePowerKw ?? 0)}
          </div>
          <div className="text-xs text-steel-400">
            of {fmtKw(asset.rated_power_kw)} rated
          </div>
        </div>
        {openAlarms > 0 && (
          <span className="inline-flex items-center gap-1 rounded-sm border border-signal-fault/30 bg-signal-fault/10 px-2 py-0.5 text-xs font-medium text-signal-fault">
            {openAlarms} alarm{openAlarms === 1 ? "" : "s"}
          </span>
        )}
      </div>

      <div className="space-y-1">
        <div className="h-1.5 w-full overflow-hidden rounded-sm bg-steel-700">
          <div
            className={clsx("h-full transition-all", s.dot)}
            style={{ width: `${utilisation}%` }}
          />
        </div>
        <div className="flex items-center justify-between text-[11px] text-steel-400">
          <span>{utilisation}% load</span>
          <span>last seen {fmtRelativeTime(lastSeen)}</span>
        </div>
      </div>
    </button>
  );
}
