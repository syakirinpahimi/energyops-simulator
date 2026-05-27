"use client";

import clsx from "clsx";
import type { Site } from "@/lib/types";

interface Props {
  sites: Site[];
  value: string | null;
  onChange: (siteId: string) => void;
  className?: string;
}

export function SiteSelector({ sites, value, onChange, className }: Props) {
  return (
    <div className={clsx("flex items-center gap-2", className)}>
      <label className="text-xs uppercase tracking-wider text-steel-400" htmlFor="site-selector">
        Site
      </label>
      <select
        id="site-selector"
        value={value ?? ""}
        onChange={(e) => onChange(e.target.value)}
        className="rounded-sm border border-steel-600 bg-steel-800 px-2 py-1.5 font-mono text-sm text-steel-50 focus:border-accent focus:outline-none focus:ring-1 focus:ring-accent"
      >
        {sites.map((s) => (
          <option key={s.id} value={s.id}>
            {s.name}
          </option>
        ))}
      </select>
    </div>
  );
}
