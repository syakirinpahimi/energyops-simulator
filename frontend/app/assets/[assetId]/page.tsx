"use client";

import { useEffect, useMemo, useState } from "react";
import { useParams, useRouter } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import type {
  Alarm,
  Asset,
  AssetSnapshot,
  Paginated,
  Sensor,
  TelemetrySeries
} from "@/lib/types";
import { statusToUi } from "@/lib/types";
import { connectTelemetry } from "@/lib/ws";
import { StatusChip } from "@/components/StatusBadge";
import { TrendChart } from "@/components/TrendChart";
import { AlarmTable } from "@/components/AlarmTable";
import { fmtKw, fmtNumber, fmtRelativeTime } from "@/lib/format";
import { useAuth } from "@/components/providers/AuthProvider";
import { can } from "@/lib/permissions";

export default function AssetDetailPage() {
  const params = useParams<{ assetId: string }>();
  const assetId = params.assetId;
  const router = useRouter();
  const { user } = useAuth();

  const [asset, setAsset] = useState<Asset | null>(null);
  const [sensors, setSensors] = useState<Sensor[]>([]);
  const [snapshot, setSnapshot] = useState<AssetSnapshot | null>(null);
  const [series, setSeries] = useState<TelemetrySeries | null>(null);
  const [metric, setMetric] = useState<string>("power_kw");
  const [alarms, setAlarms] = useState<Alarm[]>([]);
  const [livePoint, setLivePoint] = useState<number | null>(null);

  useEffect(() => {
    let cancel = false;
    api<Asset>(`/api/v1/assets/${assetId}`).then((a) => !cancel && setAsset(a));
    api<Sensor[]>(`/api/v1/assets/${assetId}/sensors`).then((s) => !cancel && setSensors(s));
    api<AssetSnapshot>(`/api/v1/assets/${assetId}/snapshot`).then(
      (s) => !cancel && setSnapshot(s)
    );
    api<Paginated<Alarm>>("/api/v1/alarms", { query: { asset_id: assetId } }).then(
      (r) => !cancel && setAlarms(r.items.filter((x) => x.asset_id === assetId))
    );
    return () => {
      cancel = true;
    };
  }, [assetId]);

  useEffect(() => {
    let cancel = false;
    api<TelemetrySeries>("/api/v1/telemetry", {
      query: {
        asset_id: assetId,
        metric,
        from: new Date(Date.now() - 60 * 60 * 1000).toISOString(),
        to: new Date().toISOString(),
        bucket: "1m"
      }
    }).then((s) => !cancel && setSeries(s));
    return () => {
      cancel = true;
    };
  }, [assetId, metric]);

  useEffect(() => {
    const handle = connectTelemetry(
      (msg) => {
        if (msg.type !== "telemetry") return;
        if (msg.asset_id !== assetId) return;
        if (msg.metric === metric) {
          setLivePoint(msg.value);
          setSeries((prev) =>
            prev
              ? {
                  ...prev,
                  points: [...prev.points.slice(-59), { ts: msg.ts, value: msg.value }]
                }
              : prev
          );
        }
      },
      { assetIds: [assetId] }
    );
    return () => handle.close();
  }, [assetId, metric]);

  const canAck = can(user?.role, "alarm.ack");
  const canResolve = can(user?.role, "alarm.resolve");
  const showDiagnostics = can(user?.role, "asset.edit");
  const ui = asset ? statusToUi(asset.status) : "offline";

  const ackAlarm = async (a: Alarm, note: string) => {
    const updated = await api<Alarm>(`/api/v1/alarms/${a.id}/ack`, {
      method: "POST",
      body: { note }
    });
    setAlarms((prev) => prev.map((x) => (x.id === updated.id ? updated : x)));
  };
  const resolveAlarm = async (a: Alarm, note: string) => {
    const updated = await api<Alarm>(`/api/v1/alarms/${a.id}/resolve`, {
      method: "POST",
      body: { note }
    });
    setAlarms((prev) => prev.map((x) => (x.id === updated.id ? updated : x)));
  };

  const metricsList = useMemo(() => sensors.map((s) => s.metric), [sensors]);
  const currentSensor = sensors.find((s) => s.metric === metric);

  if (!asset) {
    return (
      <div className="flex min-h-[calc(100vh-76px)] items-center justify-center text-steel-400">
        Loading asset…
      </div>
    );
  }

  return (
    <div className="grid-bg flex min-h-[calc(100vh-76px)] flex-col gap-4 p-4">
      <div className="flex flex-wrap items-center gap-3 text-xs text-steel-400">
        <button
          onClick={() => router.back()}
          className="rounded-sm border border-steel-600 px-2 py-1 hover:bg-steel-800"
        >
          ← Back
        </button>
        <span className="font-mono uppercase tracking-widest">{asset.asset_type}</span>
        <span>·</span>
        <Link href="/sites" className="hover:underline">
          Sites
        </Link>
      </div>

      <header className="panel flex flex-wrap items-center justify-between gap-3 p-4">
        <div className="flex items-center gap-3">
          <div>
            <h1 className="text-xl font-semibold text-steel-50">{asset.name}</h1>
            <div className="text-xs text-steel-400">
              Rated {fmtKw(asset.rated_power_kw)} · last seen{" "}
              {fmtRelativeTime(snapshot?.last_seen)}
            </div>
          </div>
        </div>
        <div className="flex items-center gap-3">
          <StatusChip state={ui} />
          {snapshot && snapshot.open_alarms > 0 && (
            <span className="rounded-sm border border-signal-fault/40 bg-signal-fault/10 px-2 py-1 text-xs font-medium text-signal-fault">
              {snapshot.open_alarms} open alarm{snapshot.open_alarms === 1 ? "" : "s"}
            </span>
          )}
        </div>
      </header>

      {/* Live metric tiles */}
      <section className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {sensors.map((s) => {
          const val =
            s.metric === metric && livePoint !== null
              ? livePoint
              : snapshot?.metrics[s.metric]?.value;
          return (
            <button
              key={s.id}
              type="button"
              onClick={() => setMetric(s.metric)}
              className={`panel p-3 text-left transition-colors ${
                s.metric === metric ? "border-accent" : "hover:border-steel-500"
              }`}
            >
              <div className="text-[11px] uppercase tracking-wider text-steel-300">
                {s.metric}
              </div>
              <div className="mt-1 font-mono text-2xl text-steel-50 tabular-nums">
                {fmtNumber(val ?? 0, 1)}
                <span className="ml-1 text-xs text-steel-400">{s.unit}</span>
              </div>
            </button>
          );
        })}
      </section>

      {/* Trend chart */}
      <section className="panel">
        <div className="panel-header">
          <span className="panel-title">
            Trend · {metric}
            {currentSensor && (
              <span className="ml-2 font-mono text-[11px] text-steel-500">
                {currentSensor.unit}
              </span>
            )}
          </span>
          <div className="flex items-center gap-1.5">
            {metricsList.map((m) => (
              <button
                key={m}
                onClick={() => setMetric(m)}
                className={`rounded-sm border px-2 py-0.5 text-[11px] font-mono ${
                  m === metric
                    ? "border-accent text-accent"
                    : "border-steel-600 text-steel-300 hover:bg-steel-700"
                }`}
              >
                {m}
              </button>
            ))}
          </div>
        </div>
        <div className="p-3">
          <TrendChart type="line" data={series?.points ?? []} unit={currentSensor?.unit} />
        </div>
      </section>

      {showDiagnostics && (
        <section className="panel">
          <div className="panel-header">
            <span className="panel-title">Diagnostics · engineer view</span>
            <span className="font-mono text-[11px] text-steel-500">
              metadata snapshot
            </span>
          </div>
          <pre className="overflow-auto p-3 font-mono text-xs text-steel-300">
            {JSON.stringify(
              {
                asset_id: asset.id,
                rated_power_kw: asset.rated_power_kw,
                status: asset.status,
                metadata: asset.metadata ?? {},
                snapshot
              },
              null,
              2
            )}
          </pre>
        </section>
      )}

      <section className="space-y-2">
        <h2 className="text-sm font-medium uppercase tracking-widest text-steel-300">
          Alarms for this asset
        </h2>
        <AlarmTable
          alarms={alarms}
          assetNameById={{ [asset.id]: asset.name }}
          canAck={canAck}
          canResolve={canResolve}
          onAck={ackAlarm}
          onResolve={resolveAlarm}
        />
      </section>
    </div>
  );
}
