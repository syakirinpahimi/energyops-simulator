"use client";

import Link from "next/link";
import type { Alarm } from "@/lib/types";

interface Props {
  alarms: Alarm[];
  assetNameById?: Record<string, string>;
}

export function AlarmBanner({ alarms, assetNameById = {} }: Props) {
  const open = alarms.filter((a) => a.state === "OPEN");
  if (open.length === 0) {
    return (
      <div className="flex items-center justify-between rounded-md border border-signal-run/30 bg-signal-run/5 px-4 py-2 text-sm text-signal-run">
        <span className="font-medium">All clear · no active alarms</span>
        <Link href="/alarms" className="text-xs uppercase tracking-wider hover:underline">
          View history
        </Link>
      </div>
    );
  }

  const top = open[0];
  return (
    <div className="flex flex-wrap items-center justify-between gap-3 rounded-md border border-signal-fault/40 bg-signal-fault/10 px-4 py-2 text-sm">
      <div className="flex items-center gap-3">
        <span className="inline-flex h-2.5 w-2.5 animate-pulse rounded-full bg-signal-fault ring-4 ring-signal-fault/30" />
        <span className="font-mono text-xs uppercase tracking-widest text-signal-fault">
          {open.length} active alarm{open.length === 1 ? "" : "s"}
        </span>
        <span className="text-steel-100">
          {assetNameById[top.asset_id] ?? top.asset_id} ·{" "}
          <span className="text-steel-300">{top.message}</span>
        </span>
      </div>
      <Link
        href="/alarms"
        className="rounded-sm border border-signal-fault/40 px-3 py-1 text-xs font-medium uppercase tracking-wider text-signal-fault hover:bg-signal-fault/20"
      >
        Open alarm panel
      </Link>
    </div>
  );
}
