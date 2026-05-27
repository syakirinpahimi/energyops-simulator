"use client";

import clsx from "clsx";
import { useMemo, useState } from "react";
import type { Area, Asset, Site } from "@/lib/types";
import { statusToUi } from "@/lib/types";
import { StatusDot } from "./StatusBadge";

interface Props {
  sites: Site[];
  areas: Area[];
  assets: Asset[];
  selectedAssetId?: string | null;
  onSelectAsset?: (a: Asset) => void;
}

export function AssetTree({ sites, areas, assets, selectedAssetId, onSelectAsset }: Props) {
  const [expandedSites, setExpandedSites] = useState<Set<string>>(new Set(sites.map((s) => s.id)));
  const [expandedAreas, setExpandedAreas] = useState<Set<string>>(new Set());

  const grouped = useMemo(() => {
    const bySite: Record<string, { site: Site; areas: { area: Area; assets: Asset[] }[] }> = {};
    for (const s of sites) bySite[s.id] = { site: s, areas: [] };
    for (const ar of areas) {
      const bucket = bySite[ar.site_id];
      if (!bucket) continue;
      bucket.areas.push({ area: ar, assets: assets.filter((a) => a.area_id === ar.id) });
    }
    return Object.values(bySite);
  }, [sites, areas, assets]);

  const toggle = (set: Set<string>, setter: (s: Set<string>) => void, id: string) => {
    const n = new Set(set);
    n.has(id) ? n.delete(id) : n.add(id);
    setter(n);
  };

  return (
    <nav className="text-sm">
      <div className="px-3 pb-2 pt-3 text-[11px] uppercase tracking-widest text-steel-400">
        Plant Hierarchy
      </div>
      <ul className="space-y-0.5">
        {grouped.map(({ site, areas: a }) => {
          const open = expandedSites.has(site.id);
          return (
            <li key={site.id}>
              <button
                type="button"
                onClick={() => toggle(expandedSites, setExpandedSites, site.id)}
                className="flex w-full items-center justify-between rounded-sm px-3 py-1.5 text-left hover:bg-steel-700/40"
              >
                <span className="flex items-center gap-2">
                  <Caret open={open} />
                  <span className="font-medium text-steel-100">{site.name}</span>
                </span>
                <span className="text-[11px] text-steel-500">{a.length}</span>
              </button>
              {open && (
                <ul className="mt-0.5 space-y-0.5 border-l border-steel-700/60 pl-3">
                  {a.map(({ area, assets: assetsInArea }) => {
                    const aopen = expandedAreas.has(area.id);
                    return (
                      <li key={area.id}>
                        <button
                          type="button"
                          onClick={() => toggle(expandedAreas, setExpandedAreas, area.id)}
                          className="flex w-full items-center justify-between rounded-sm px-2 py-1 text-left text-steel-200 hover:bg-steel-700/40"
                        >
                          <span className="flex items-center gap-2">
                            <Caret open={aopen} />
                            <span>{area.name}</span>
                          </span>
                          <span className="text-[11px] text-steel-500">{assetsInArea.length}</span>
                        </button>
                        {aopen && (
                          <ul className="mt-0.5 space-y-0.5 border-l border-steel-700/60 pl-3">
                            {assetsInArea.map((as) => (
                              <li key={as.id}>
                                <button
                                  type="button"
                                  onClick={() => onSelectAsset?.(as)}
                                  className={clsx(
                                    "flex w-full items-center gap-2 rounded-sm px-2 py-1 text-left",
                                    selectedAssetId === as.id
                                      ? "bg-accent/10 text-accent"
                                      : "text-steel-300 hover:bg-steel-700/40"
                                  )}
                                >
                                  <StatusDot state={statusToUi(as.status)} />
                                  <span className="truncate">{as.name}</span>
                                  <span className="ml-auto font-mono text-[11px] text-steel-500">
                                    {as.asset_type}
                                  </span>
                                </button>
                              </li>
                            ))}
                          </ul>
                        )}
                      </li>
                    );
                  })}
                </ul>
              )}
            </li>
          );
        })}
      </ul>
    </nav>
  );
}

function Caret({ open }: { open: boolean }) {
  return (
    <span
      className={clsx(
        "inline-block h-2 w-2 border-r border-b border-steel-400 transition-transform",
        open ? "rotate-45" : "-rotate-45"
      )}
    />
  );
}
