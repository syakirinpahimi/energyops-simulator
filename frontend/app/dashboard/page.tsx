"use client";

import { useEffect, useMemo, useState } from "react";
import { useRouter } from "next/navigation";
import { api } from "@/lib/api";
import type {
  Alarm,
  Asset,
  Site,
  TelemetrySeries,
  Paginated
} from "@/lib/types";
import { connectTelemetry } from "@/lib/ws";
import { SiteSelector } from "@/components/SiteSelector";
import { StatusCard } from "@/components/StatusCard";
import { EnergyKpiCard } from "@/components/EnergyKpiCard";
import { TrendChart } from "@/components/TrendChart";
import { AlarmBanner } from "@/components/AlarmBanner";
import { useAuth } from "@/components/providers/AuthProvider";

export default function DashboardPage() {
  const { user } = useAuth();
  const router = useRouter();
  const [sites, setSites] = useState<Site[]>([]);
  const [siteId, setSiteId] = useState<string | null>(null);
  const [assets, setAssets] = useState<Asset[]>([]);
  const [alarms, setAlarms] = useState<Alarm[]>([]);
  const [siteLoad, setSiteLoad] = useState<TelemetrySeries | null>(null);
  const [livePower, setLivePower] = useState<Record<string, number>>({});
  const [lastSeen, setLastSeen] = useState<Record<string, string>>({});

  // Initial load: sites
  useEffect(() => {
    let cancel = false;
    api<Site[]>("/api/v1/sites").then((s) => {
      if (cancel) return;
      setSites(s);
      if (s[0]) setSiteId(s[0].id);
    });
    api<Paginated<Alarm>>("/api/v1/alarms", { query: { state: "OPEN" } }).then((r) => {
      if (!cancel) setAlarms(r.items);
    });
    return () => {
      cancel = true;
    };
  }, []);

  // Per-site assets + trend
  useEffect(() => {
    if (!siteId) return;
    let cancel = false;
    api<Asset[]>("/api/v1/assets", { query: { site_id: siteId } }).then((a) => {
      if (!cancel) setAssets(a);
    });
    // Use first asset of the site as a proxy for site load trend.
    api<Asset[]>("/api/v1/assets", { query: { site_id: siteId } })
      .then((a) => a[0])
      .then((primary) => {
        if (!primary) return;
        return api<TelemetrySeries>("/api/v1/telemetry", {
          query: {
            asset_id: primary.id,
            metric: "power_kw",
            from: new Date(Date.now() - 60 * 60 * 1000).toISOString(),
            to: new Date().toISOString(),
            bucket: "1m"
          }
        });
      })
      .then((s) => {
        if (s && !cancel) setSiteLoad(s);
      });
    return () => {
      cancel = true;
    };
  }, [siteId]);

  // Live WS for current site assets
  useEffect(() => {
    if (assets.length === 0) return;
    const handle = connectTelemetry(
      (msg) => {
        if (msg.type !== "telemetry") return;
        if (msg.metric !== "power_kw") return;
        setLivePower((prev) => ({ ...prev, [msg.asset_id]: msg.value }));
        setLastSeen((prev) => ({ ...prev, [msg.asset_id]: msg.ts }));
      },
      { assetIds: assets.map((a) => a.id) }
    );
    return () => handle.close();
  }, [assets]);

  const totals = useMemo(() => {
    const sumLive = Object.values(livePower).reduce((a, b) => a + b, 0);
    const rated = assets.reduce((a, x) => a + (x.rated_power_kw ?? 0), 0);
    const running = assets.filter((a) => a.status === "online").length;
    const fault = assets.filter((a) => a.status === "fault").length;
    return { sumLive, rated, running, fault };
  }, [livePower, assets]);

  const energyByAsset = useMemo(
    () =>
      assets.map((a) => ({
        label: a.name.length > 14 ? a.name.slice(0, 13) + "…" : a.name,
        value: +(((livePower[a.id] ?? (a.rated_power_kw ?? 0) * 0.65) * 24) / 1000).toFixed(2) * 10
      })),
    [assets, livePower]
  );

  const assetNameById = useMemo(() => {
    const m: Record<string, string> = {};
    for (const a of assets) m[a.id] = a.name;
    return m;
  }, [assets]);

  const siteAlarms = alarms.filter((a) => assets.some((x) => x.id === a.asset_id));

  return (
    <div className="grid-bg flex min-h-[calc(100vh-76px)] flex-col gap-4 p-4">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-steel-50">Operations Dashboard</h1>
          <p className="text-xs text-steel-400">
            Live equipment status, energy KPIs, and active alarms.
          </p>
        </div>
        <SiteSelector sites={sites} value={siteId} onChange={setSiteId} />
      </div>

      <AlarmBanner alarms={siteAlarms} assetNameById={assetNameById} />

      <section className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <EnergyKpiCard label="Live Site Load" energyKwh={totals.sumLive} unit="kW" />
        <EnergyKpiCard
          label="Today's Energy"
          energyKwh={Math.round(totals.sumLive * 18)}
          deltaPct={-3.4}
          costEstimate={Math.round(totals.sumLive * 18 * 0.42)}
        />
        <EnergyKpiCard label="Running Assets" energyKwh={totals.running} unit="" />
        <EnergyKpiCard label="Faulted" energyKwh={totals.fault} unit="" />
      </section>

      <section className="grid grid-cols-1 gap-4 lg:grid-cols-3">
        <div className="panel lg:col-span-2">
          <div className="panel-header">
            <span className="panel-title">Site Load Trend · last hour</span>
            <span className="font-mono text-[11px] text-steel-500">power_kw · 1m bucket</span>
          </div>
          <div className="p-3">
            <TrendChart type="area" data={siteLoad?.points ?? []} unit="kW" />
          </div>
        </div>

        <div className="panel">
          <div className="panel-header">
            <span className="panel-title">Energy by Asset · est 24h</span>
            <span className="font-mono text-[11px] text-steel-500">kWh</span>
          </div>
          <div className="p-3">
            <TrendChart type="bar" data={energyByAsset} unit="kWh" color="#38bdf8" />
          </div>
        </div>
      </section>

      <section className="space-y-2">
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-medium uppercase tracking-widest text-steel-300">
            Equipment status
          </h2>
          <span className="text-[11px] text-steel-500">
            {assets.length} asset{assets.length === 1 ? "" : "s"}
          </span>
        </div>
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3 xl:grid-cols-4">
          {assets.map((a) => (
            <StatusCard
              key={a.id}
              asset={a}
              livePowerKw={livePower[a.id]}
              lastSeen={lastSeen[a.id]}
              openAlarms={alarms.filter((x) => x.asset_id === a.id && x.state === "OPEN").length}
              onClick={() => router.push(`/assets/${a.id}`)}
            />
          ))}
        </div>
      </section>
    </div>
  );
}
