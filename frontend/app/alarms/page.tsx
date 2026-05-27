"use client";

import { useEffect, useMemo, useState } from "react";
import { api } from "@/lib/api";
import type { Alarm, Asset, Paginated } from "@/lib/types";
import { AlarmTable } from "@/components/AlarmTable";
import { useAuth } from "@/components/providers/AuthProvider";
import { can } from "@/lib/permissions";

const FILTERS = [
  { key: "OPEN", label: "Open" },
  { key: "ACK", label: "Acknowledged" },
  { key: "RESOLVED", label: "Resolved" },
  { key: "", label: "All" }
] as const;

export default function AlarmsPage() {
  const { user } = useAuth();
  const [alarms, setAlarms] = useState<Alarm[]>([]);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [filter, setFilter] = useState<typeof FILTERS[number]["key"]>("OPEN");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancel = false;
    api<Asset[]>("/api/v1/assets").then((a) => !cancel && setAssets(a));
    return () => {
      cancel = true;
    };
  }, []);

  useEffect(() => {
    let cancel = false;
    setLoading(true);
    api<Paginated<Alarm>>("/api/v1/alarms", {
      query: filter ? { state: filter } : {}
    })
      .then((r) => !cancel && setAlarms(r.items))
      .finally(() => !cancel && setLoading(false));
    return () => {
      cancel = true;
    };
  }, [filter]);

  const assetNameById = useMemo(() => {
    const m: Record<string, string> = {};
    for (const a of assets) m[a.id] = a.name;
    return m;
  }, [assets]);

  const canAck = can(user?.role, "alarm.ack");
  const canResolve = can(user?.role, "alarm.resolve");

  const ack = async (a: Alarm, note: string) => {
    const updated = await api<Alarm>(`/api/v1/alarms/${a.id}/ack`, {
      method: "POST",
      body: { note }
    });
    setAlarms((prev) =>
      prev.map((x) => (x.id === updated.id ? updated : x))
    );
  };
  const resolve = async (a: Alarm, note: string) => {
    const updated = await api<Alarm>(`/api/v1/alarms/${a.id}/resolve`, {
      method: "POST",
      body: { note }
    });
    setAlarms((prev) =>
      prev.map((x) => (x.id === updated.id ? updated : x))
    );
  };

  const counts = useMemo(() => {
    return {
      OPEN: alarms.filter((a) => a.state === "OPEN").length,
      ACK: alarms.filter((a) => a.state === "ACK").length,
      RESOLVED: alarms.filter((a) => a.state === "RESOLVED").length
    };
  }, [alarms]);

  return (
    <div className="grid-bg min-h-[calc(100vh-76px)] space-y-4 p-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-steel-50">Alarms</h1>
          <p className="text-xs text-steel-400">
            Acknowledge open alarms · {canResolve ? "engineers can resolve closed cases" : "operators can acknowledge"}
          </p>
        </div>
        <div className="flex items-center gap-1">
          {FILTERS.map((f) => (
            <button
              key={f.key}
              type="button"
              onClick={() => setFilter(f.key)}
              className={`rounded-sm border px-3 py-1 text-xs font-medium uppercase tracking-wider ${
                filter === f.key
                  ? "border-accent text-accent"
                  : "border-steel-600 text-steel-300 hover:bg-steel-700"
              }`}
            >
              {f.label}
            </button>
          ))}
        </div>
      </div>

      <div className="grid grid-cols-3 gap-3">
        <Stat label="Open" value={counts.OPEN} tone="fault" />
        <Stat label="Acknowledged" value={counts.ACK} tone="warn" />
        <Stat label="Resolved" value={counts.RESOLVED} tone="run" />
      </div>

      {loading ? (
        <div className="rounded-md border border-steel-700 bg-steel-800 p-6 text-center text-steel-400">
          Loading alarms…
        </div>
      ) : (
        <AlarmTable
          alarms={alarms}
          assetNameById={assetNameById}
          canAck={canAck}
          canResolve={canResolve}
          onAck={ack}
          onResolve={resolve}
        />
      )}
    </div>
  );
}

function Stat({ label, value, tone }: { label: string; value: number; tone: "fault" | "warn" | "run" }) {
  const colour =
    tone === "fault" ? "text-signal-fault" : tone === "warn" ? "text-signal-warn" : "text-signal-run";
  return (
    <div className="panel p-3">
      <div className="text-[11px] uppercase tracking-wider text-steel-300">{label}</div>
      <div className={`font-mono text-2xl tabular-nums ${colour}`}>{value}</div>
    </div>
  );
}
