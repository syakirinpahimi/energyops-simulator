"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { AuditEntry, Paginated } from "@/lib/types";
import { AuditLogTable } from "@/components/AuditLogTable";
import { useAuth } from "@/components/providers/AuthProvider";
import { can } from "@/lib/permissions";

export default function AuditLogPage() {
  const { user } = useAuth();
  const [entries, setEntries] = useState<AuditEntry[]>([]);
  const [filter, setFilter] = useState("");

  useEffect(() => {
    let cancel = false;
    api<Paginated<AuditEntry>>("/api/v1/audit").then(
      (r) => !cancel && setEntries(r.items)
    );
    return () => {
      cancel = true;
    };
  }, []);

  if (!can(user?.role, "audit.view")) {
    return (
      <div className="grid-bg flex min-h-[calc(100vh-76px)] items-center justify-center">
        <div className="panel max-w-md p-6 text-center">
          <h1 className="text-lg font-semibold text-steel-50">Access denied</h1>
          <p className="mt-2 text-sm text-steel-400">
            Audit log is restricted to engineer, manager, and admin roles.
          </p>
        </div>
      </div>
    );
  }

  const filtered = filter
    ? entries.filter(
        (e) =>
          e.action.toLowerCase().includes(filter.toLowerCase()) ||
          e.actor_email.toLowerCase().includes(filter.toLowerCase()) ||
          (e.target_id ?? "").toLowerCase().includes(filter.toLowerCase())
      )
    : entries;

  return (
    <div className="grid-bg min-h-[calc(100vh-76px)] space-y-4 p-4">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div>
          <h1 className="text-lg font-semibold text-steel-50">Audit Log</h1>
          <p className="text-xs text-steel-400">
            Authoritative record of operator actions, alarm transitions, and report generation.
          </p>
        </div>
        <input
          type="search"
          value={filter}
          onChange={(e) => setFilter(e.target.value)}
          placeholder="Filter by action, actor, target…"
          className="w-72 rounded-sm border border-steel-600 bg-steel-800 px-3 py-1.5 text-sm focus:border-accent focus:outline-none"
        />
      </div>
      <AuditLogTable entries={filtered} />
    </div>
  );
}
