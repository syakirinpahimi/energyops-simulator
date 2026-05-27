"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, api } from "@/lib/api";
import { canViewAudit, useUser } from "@/lib/auth";
import { ErrorBanner, PageHeader, Section } from "@/components/Shell";
import type { AuditEntry, AuditList } from "@/lib/types";

const ACTIONS: string[] = [
  "alarm.ack",
  "alarm.resolve",
  "auth.login",
  "auth.login_failed",
  "report.create",
  "asset.create",
  "asset.update",
  "asset.delete",
];

function fmtTs(ts: string): string {
  try {
    return new Date(ts).toLocaleString();
  } catch {
    return ts;
  }
}

function fmtDetails(meta: Record<string, unknown>): string {
  if (!meta || Object.keys(meta).length === 0) return "-";
  // Compact one-line dump; the audit page is a high-level overview, the
  // raw row is available in the API for deeper inspection.
  return Object.entries(meta)
    .map(([k, v]) => `${k}=${typeof v === "string" ? v : JSON.stringify(v)}`)
    .join("  ");
}

export default function AuditPage() {
  const { user } = useUser();
  const [items, setItems] = useState<AuditEntry[]>([]);
  const [action, setAction] = useState<string>("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const allowed = canViewAudit(user);

  const reload = useCallback(async () => {
    if (!allowed) return;
    setLoading(true);
    setError(null);
    try {
      const data = await api<AuditList>("/audit-log", { query: { action: action || undefined, limit: 200 } });
      setItems(data.items);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Unable to load audit log.");
    } finally {
      setLoading(false);
    }
  }, [allowed, action]);

  useEffect(() => {
    reload();
  }, [reload]);

  if (!allowed) {
    return (
      <>
        <PageHeader title="Audit log" />
        <ErrorBanner message="Engineer role or above required to view the audit log." />
      </>
    );
  }

  return (
    <>
      <PageHeader
        title="Audit log"
        subtitle="Recent operator and system actions."
        right={
          <div className="flex gap-2">
            <select className="input" value={action} onChange={(e) => setAction(e.target.value)}>
              <option value="">All actions</option>
              {ACTIONS.map((a) => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
            </select>
            <button onClick={reload} className="btn" disabled={loading}>
              {loading ? "Loading..." : "Refresh"}
            </button>
          </div>
        }
      />
      {error ? <ErrorBanner message={error} /> : null}
      <Section>
        <div className="overflow-x-auto">
          <table className="table">
            <thead>
              <tr>
                <th>Timestamp</th>
                <th>User</th>
                <th>Action</th>
                <th>Entity</th>
                <th>Details</th>
              </tr>
            </thead>
            <tbody>
              {items.length === 0 && !loading ? (
                <tr>
                  <td colSpan={5} className="py-8 text-center text-muted">
                    No audit entries match this filter.
                  </td>
                </tr>
              ) : null}
              {items.map((row) => (
                <tr key={row.id}>
                  <td className="whitespace-nowrap text-muted">{fmtTs(row.ts)}</td>
                  <td className="text-slate-100">{row.actor_email}</td>
                  <td>
                    <span className="badge badge-info">{row.action}</span>
                  </td>
                  <td className="text-slate-300">
                    {row.target_type ? (
                      <div>
                        <div>{row.target_type}</div>
                        {row.target_id ? <div className="text-xs text-muted">{row.target_id.slice(0, 8)}</div> : null}
                      </div>
                    ) : (
                      "-"
                    )}
                  </td>
                  <td className="font-mono text-xs text-slate-300">{fmtDetails(row.metadata)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Section>
    </>
  );
}
