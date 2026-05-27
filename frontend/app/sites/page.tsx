"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { api } from "@/lib/api";
import type { Area, Asset, Site } from "@/lib/types";
import { statusToUi } from "@/lib/types";
import { StatusDot } from "@/components/StatusBadge";
import { fmtKw } from "@/lib/format";

export default function SitesPage() {
  const [sites, setSites] = useState<Site[]>([]);
  const [areas, setAreas] = useState<Area[]>([]);
  const [assets, setAssets] = useState<Asset[]>([]);

  useEffect(() => {
    let cancel = false;
    Promise.all([
      api<Site[]>("/api/v1/sites"),
      api<Area[]>("/api/v1/areas"),
      api<Asset[]>("/api/v1/assets")
    ]).then(([s, ar, a]) => {
      if (cancel) return;
      setSites(s);
      setAreas(ar);
      setAssets(a);
    });
    return () => {
      cancel = true;
    };
  }, []);

  return (
    <div className="grid-bg min-h-[calc(100vh-76px)] p-4">
      <div className="mb-4 flex items-end justify-between">
        <div>
          <h1 className="text-lg font-semibold text-steel-50">Sites</h1>
          <p className="text-xs text-steel-400">
            Plant hierarchy: company → site → area → asset.
          </p>
        </div>
        <span className="text-xs text-steel-500">
          {sites.length} sites · {assets.length} assets
        </span>
      </div>

      <div className="grid grid-cols-1 gap-4 lg:grid-cols-2 xl:grid-cols-3">
        {sites.map((s) => {
          const siteAreas = areas.filter((a) => a.site_id === s.id);
          const siteAssets = assets.filter((a) =>
            siteAreas.some((x) => x.id === a.area_id)
          );
          const ratedSum = siteAssets.reduce((acc, a) => acc + (a.rated_power_kw ?? 0), 0);
          const faulted = siteAssets.filter((a) => a.status === "fault").length;
          return (
            <div key={s.id} className="panel overflow-hidden">
              <div className="panel-header">
                <div>
                  <span className="panel-title">{s.name}</span>
                  <div className="text-[11px] text-steel-500">{s.timezone ?? "—"}</div>
                </div>
                <Link
                  href={`/dashboard?site=${s.id}`}
                  className="rounded-sm border border-steel-600 px-2 py-1 text-xs text-steel-200 hover:bg-steel-700"
                >
                  Open
                </Link>
              </div>
              <div className="grid grid-cols-3 border-b border-steel-700 text-xs">
                <Stat label="Areas" value={siteAreas.length} />
                <Stat label="Assets" value={siteAssets.length} />
                <Stat label="Rated" value={fmtKw(ratedSum)} />
              </div>
              <ul className="max-h-72 divide-y divide-steel-700/60 overflow-auto">
                {siteAreas.map((a) => {
                  const inArea = siteAssets.filter((x) => x.area_id === a.id);
                  return (
                    <li key={a.id} className="px-3 py-2">
                      <div className="mb-1 flex items-center justify-between">
                        <span className="text-sm text-steel-100">{a.name}</span>
                        <span className="text-[11px] text-steel-500">
                          {inArea.length} asset{inArea.length === 1 ? "" : "s"}
                        </span>
                      </div>
                      <div className="grid grid-cols-2 gap-1.5 sm:grid-cols-3">
                        {inArea.map((ax) => (
                          <Link
                            key={ax.id}
                            href={`/assets/${ax.id}`}
                            className="flex items-center gap-2 rounded-sm border border-steel-700 bg-steel-900 px-2 py-1.5 text-xs hover:border-steel-500"
                          >
                            <StatusDot state={statusToUi(ax.status)} />
                            <span className="truncate text-steel-200">{ax.name}</span>
                          </Link>
                        ))}
                      </div>
                    </li>
                  );
                })}
              </ul>
              {faulted > 0 && (
                <div className="border-t border-steel-700 bg-signal-fault/5 px-3 py-1.5 text-[11px] text-signal-fault">
                  {faulted} faulted asset{faulted === 1 ? "" : "s"} requires attention
                </div>
              )}
            </div>
          );
        })}
      </div>
    </div>
  );
}

function Stat({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="border-r border-steel-700 px-3 py-2 last:border-0">
      <div className="text-[11px] uppercase tracking-wider text-steel-400">{label}</div>
      <div className="font-mono text-sm text-steel-100">{value}</div>
    </div>
  );
}
