import clsx from "clsx";
import type { UiAssetState } from "@/lib/types";
import { uiStateLabel } from "@/lib/format";

const STATE_STYLES: Record<UiAssetState, { dot: string; ring: string; text: string; chip: string }> = {
  running: {
    dot: "bg-signal-run",
    ring: "ring-signal-run/30",
    text: "text-signal-run",
    chip: "bg-signal-run/10 text-signal-run border-signal-run/30"
  },
  warning: {
    dot: "bg-signal-warn",
    ring: "ring-signal-warn/30",
    text: "text-signal-warn",
    chip: "bg-signal-warn/10 text-signal-warn border-signal-warn/30"
  },
  fault: {
    dot: "bg-signal-fault",
    ring: "ring-signal-fault/30",
    text: "text-signal-fault",
    chip: "bg-signal-fault/10 text-signal-fault border-signal-fault/30"
  },
  offline: {
    dot: "bg-signal-offline",
    ring: "ring-signal-offline/30",
    text: "text-signal-offline",
    chip: "bg-signal-offline/10 text-signal-offline border-signal-offline/30"
  }
};

export function StatusDot({ state, pulse = false }: { state: UiAssetState; pulse?: boolean }) {
  const s = STATE_STYLES[state];
  return (
    <span
      aria-label={uiStateLabel(state)}
      className={clsx(
        "inline-block h-2.5 w-2.5 rounded-full ring-4",
        s.dot,
        s.ring,
        pulse && state === "fault" && "animate-pulse"
      )}
    />
  );
}

export function StatusChip({ state, className }: { state: UiAssetState; className?: string }) {
  const s = STATE_STYLES[state];
  return (
    <span
      className={clsx(
        "inline-flex items-center gap-1.5 rounded-sm border px-2 py-0.5 text-xs font-medium uppercase tracking-wider",
        s.chip,
        className
      )}
    >
      <StatusDot state={state} />
      {uiStateLabel(state)}
    </span>
  );
}

export function styleForState(state: UiAssetState) {
  return STATE_STYLES[state];
}
