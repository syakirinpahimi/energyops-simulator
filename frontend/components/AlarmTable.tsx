"use client";

import clsx from "clsx";
import { useMemo, useState } from "react";
import type { Alarm } from "@/lib/types";
import { fmtClock, fmtRelativeTime } from "@/lib/format";

interface Props {
  alarms: Alarm[];
  assetNameById?: Record<string, string>;
  canAck?: boolean;
  canResolve?: boolean;
  onAck?: (a: Alarm, note: string) => Promise<void> | void;
  onResolve?: (a: Alarm, note: string) => Promise<void> | void;
}

const SEV_STYLE = {
  critical: "text-signal-fault border-signal-fault/40 bg-signal-fault/10",
  warning: "text-signal-warn border-signal-warn/40 bg-signal-warn/10",
  info: "text-signal-info border-signal-info/40 bg-signal-info/10"
} as const;

const STATE_STYLE = {
  OPEN: "bg-signal-fault/20 text-signal-fault",
  ACK: "bg-signal-warn/20 text-signal-warn",
  RESOLVED: "bg-signal-run/20 text-signal-run"
} as const;

export function AlarmTable({
  alarms,
  assetNameById = {},
  canAck = false,
  canResolve = false,
  onAck,
  onResolve
}: Props) {
  const [busyId, setBusyId] = useState<string | null>(null);
  const [noteFor, setNoteFor] = useState<string | null>(null);
  const [note, setNote] = useState("");

  const sorted = useMemo(
    () =>
      [...alarms].sort((a, b) => {
        const order: Record<Alarm["state"], number> = { OPEN: 0, ACK: 1, RESOLVED: 2 };
        if (order[a.state] !== order[b.state]) return order[a.state] - order[b.state];
        return new Date(b.opened_at).getTime() - new Date(a.opened_at).getTime();
      }),
    [alarms]
  );

  async function handleAck(a: Alarm) {
    if (!onAck) return;
    setBusyId(a.id);
    try {
      await onAck(a, note);
    } finally {
      setBusyId(null);
      setNoteFor(null);
      setNote("");
    }
  }

  async function handleResolve(a: Alarm) {
    if (!onResolve) return;
    setBusyId(a.id);
    try {
      await onResolve(a, note);
    } finally {
      setBusyId(null);
      setNoteFor(null);
      setNote("");
    }
  }

  return (
    <div className="overflow-hidden rounded-md border border-steel-700 bg-steel-800 shadow-panel">
      <table className="w-full text-sm">
        <thead className="border-b border-steel-700 bg-steel-900/50 text-left text-[11px] uppercase tracking-wider text-steel-300">
          <tr>
            <th className="px-3 py-2 font-medium">Severity</th>
            <th className="px-3 py-2 font-medium">State</th>
            <th className="px-3 py-2 font-medium">Asset</th>
            <th className="px-3 py-2 font-medium">Code</th>
            <th className="px-3 py-2 font-medium">Message</th>
            <th className="px-3 py-2 font-medium">Opened</th>
            <th className="px-3 py-2 font-medium text-right">Actions</th>
          </tr>
        </thead>
        <tbody>
          {sorted.length === 0 && (
            <tr>
              <td colSpan={7} className="px-3 py-6 text-center text-steel-400">
                No alarms.
              </td>
            </tr>
          )}
          {sorted.map((a) => (
            <tr
              key={a.id}
              className="border-b border-steel-700/60 last:border-0 hover:bg-steel-700/30"
            >
              <td className="px-3 py-2">
                <span
                  className={clsx(
                    "inline-flex items-center rounded-sm border px-2 py-0.5 text-[11px] font-medium uppercase tracking-wider",
                    SEV_STYLE[a.severity]
                  )}
                >
                  {a.severity}
                </span>
              </td>
              <td className="px-3 py-2">
                <span
                  className={clsx(
                    "inline-flex items-center rounded-sm px-2 py-0.5 font-mono text-[11px]",
                    STATE_STYLE[a.state]
                  )}
                >
                  {a.state}
                </span>
              </td>
              <td className="px-3 py-2 text-steel-100">
                {assetNameById[a.asset_id] ?? a.asset_id}
              </td>
              <td className="px-3 py-2 font-mono text-xs text-steel-200">{a.code}</td>
              <td className="px-3 py-2 text-steel-200">{a.message}</td>
              <td className="px-3 py-2 text-steel-300">
                <div>{fmtClock(a.opened_at)}</div>
                <div className="text-[11px] text-steel-500">{fmtRelativeTime(a.opened_at)}</div>
              </td>
              <td className="px-3 py-2 text-right">
                {noteFor === a.id ? (
                  <div className="flex items-center justify-end gap-2">
                    <input
                      autoFocus
                      value={note}
                      onChange={(e) => setNote(e.target.value)}
                      placeholder="Note (optional)"
                      className="rounded-sm border border-steel-600 bg-steel-900 px-2 py-1 text-xs"
                    />
                    {a.state === "OPEN" && canAck && (
                      <button
                        type="button"
                        disabled={busyId === a.id}
                        onClick={() => handleAck(a)}
                        className="rounded-sm border border-accent/50 bg-accent/10 px-2 py-1 text-xs font-medium text-accent hover:bg-accent/20 disabled:opacity-50"
                      >
                        Confirm Ack
                      </button>
                    )}
                    {a.state !== "RESOLVED" && canResolve && (
                      <button
                        type="button"
                        disabled={busyId === a.id}
                        onClick={() => handleResolve(a)}
                        className="rounded-sm border border-signal-run/50 bg-signal-run/10 px-2 py-1 text-xs font-medium text-signal-run hover:bg-signal-run/20 disabled:opacity-50"
                      >
                        Confirm Resolve
                      </button>
                    )}
                    <button
                      type="button"
                      onClick={() => {
                        setNoteFor(null);
                        setNote("");
                      }}
                      className="rounded-sm border border-steel-600 px-2 py-1 text-xs text-steel-300 hover:bg-steel-700"
                    >
                      Cancel
                    </button>
                  </div>
                ) : (
                  <div className="flex items-center justify-end gap-2">
                    {a.state === "OPEN" && canAck && (
                      <button
                        type="button"
                        onClick={() => setNoteFor(a.id)}
                        className="rounded-sm border border-accent/40 px-2 py-1 text-xs font-medium text-accent hover:bg-accent/10"
                      >
                        Acknowledge
                      </button>
                    )}
                    {a.state === "ACK" && canResolve && (
                      <button
                        type="button"
                        onClick={() => setNoteFor(a.id)}
                        className="rounded-sm border border-signal-run/40 px-2 py-1 text-xs font-medium text-signal-run hover:bg-signal-run/10"
                      >
                        Resolve
                      </button>
                    )}
                    {a.state === "RESOLVED" && (
                      <span className="text-[11px] text-steel-500">closed</span>
                    )}
                  </div>
                )}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
