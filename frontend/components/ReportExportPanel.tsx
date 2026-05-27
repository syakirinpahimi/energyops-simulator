"use client";

import { useState } from "react";
import type { ReportSummary, Site } from "@/lib/types";
import { fmtNumber } from "@/lib/format";

interface Props {
  sites: Site[];
  recentReports: ReportSummary[];
  canGenerate: boolean;
  onGenerate: (params: {
    site_id: string;
    from: string;
    to: string;
    format: "pdf" | "csv";
  }) => Promise<ReportSummary | void>;
  onDownload?: (id: string) => Promise<void> | void;
}

function isoDay(d: Date): string {
  return d.toISOString().slice(0, 10);
}

export function ReportExportPanel({
  sites,
  recentReports,
  canGenerate,
  onGenerate,
  onDownload
}: Props) {
  const today = new Date();
  const monthAgo = new Date();
  monthAgo.setDate(today.getDate() - 30);

  const [siteId, setSiteId] = useState(sites[0]?.id ?? "");
  const [from, setFrom] = useState(isoDay(monthAgo));
  const [to, setTo] = useState(isoDay(today));
  const [format, setFormat] = useState<"pdf" | "csv">("pdf");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!canGenerate) return;
    setBusy(true);
    setError(null);
    try {
      await onGenerate({
        site_id: siteId,
        from: new Date(from).toISOString(),
        to: new Date(to).toISOString(),
        format
      });
    } catch (err) {
      setError(err instanceof Error ? err.message : "Report failed");
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="space-y-4">
      <form
        onSubmit={submit}
        className="grid grid-cols-1 gap-3 rounded-md border border-steel-700 bg-steel-800 p-4 shadow-panel sm:grid-cols-2 lg:grid-cols-5"
      >
        <Field label="Site">
          <select
            value={siteId}
            onChange={(e) => setSiteId(e.target.value)}
            className="w-full rounded-sm border border-steel-600 bg-steel-900 px-2 py-1.5 text-sm"
          >
            {sites.map((s) => (
              <option key={s.id} value={s.id}>
                {s.name}
              </option>
            ))}
          </select>
        </Field>
        <Field label="From">
          <input
            type="date"
            value={from}
            onChange={(e) => setFrom(e.target.value)}
            className="w-full rounded-sm border border-steel-600 bg-steel-900 px-2 py-1.5 font-mono text-sm"
          />
        </Field>
        <Field label="To">
          <input
            type="date"
            value={to}
            onChange={(e) => setTo(e.target.value)}
            className="w-full rounded-sm border border-steel-600 bg-steel-900 px-2 py-1.5 font-mono text-sm"
          />
        </Field>
        <Field label="Format">
          <select
            value={format}
            onChange={(e) => setFormat(e.target.value as "pdf" | "csv")}
            className="w-full rounded-sm border border-steel-600 bg-steel-900 px-2 py-1.5 text-sm uppercase"
          >
            <option value="pdf">PDF</option>
            <option value="csv">CSV</option>
          </select>
        </Field>
        <div className="flex items-end">
          <button
            type="submit"
            disabled={!canGenerate || busy}
            className="w-full rounded-sm border border-accent/50 bg-accent/10 px-3 py-2 text-sm font-medium uppercase tracking-wider text-accent hover:bg-accent/20 disabled:cursor-not-allowed disabled:opacity-40"
          >
            {busy ? "Generating…" : "Generate"}
          </button>
        </div>
        {!canGenerate && (
          <div className="col-span-full text-xs text-steel-400">
            You need the Manager or Admin role to generate reports.
          </div>
        )}
        {error && (
          <div className="col-span-full text-xs text-signal-fault">{error}</div>
        )}
      </form>

      <div className="overflow-hidden rounded-md border border-steel-700 bg-steel-800 shadow-panel">
        <table className="w-full text-sm">
          <thead className="border-b border-steel-700 bg-steel-900/50 text-left text-[11px] uppercase tracking-wider text-steel-300">
            <tr>
              <th className="px-3 py-2 font-medium">Created</th>
              <th className="px-3 py-2 font-medium">Kind</th>
              <th className="px-3 py-2 font-medium">Format</th>
              <th className="px-3 py-2 font-medium">Status</th>
              <th className="px-3 py-2 font-medium">Size</th>
              <th className="px-3 py-2 font-medium text-right">Download</th>
            </tr>
          </thead>
          <tbody>
            {recentReports.length === 0 && (
              <tr>
                <td colSpan={6} className="px-3 py-6 text-center text-steel-400">
                  No reports yet.
                </td>
              </tr>
            )}
            {recentReports.map((r) => (
              <tr key={r.id} className="border-b border-steel-700/60 last:border-0">
                <td className="px-3 py-2 text-steel-200">{new Date(r.created_at).toLocaleString()}</td>
                <td className="px-3 py-2 capitalize text-steel-200">{r.kind}</td>
                <td className="px-3 py-2 font-mono uppercase text-steel-200">{r.format}</td>
                <td className="px-3 py-2 capitalize text-steel-200">{r.status}</td>
                <td className="px-3 py-2 text-steel-300">
                  {r.file_size_bytes ? `${fmtNumber(r.file_size_bytes / 1024, 0)} KB` : "—"}
                </td>
                <td className="px-3 py-2 text-right">
                  {r.status === "ready" && onDownload && (
                    <button
                      type="button"
                      onClick={() => onDownload(r.id)}
                      className="rounded-sm border border-steel-600 px-2 py-1 text-xs text-steel-100 hover:bg-steel-700"
                    >
                      Download
                    </button>
                  )}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </section>
  );
}

function Field({ label, children }: { label: string; children: React.ReactNode }) {
  return (
    <label className="flex flex-col gap-1">
      <span className="text-[11px] uppercase tracking-wider text-steel-400">{label}</span>
      {children}
    </label>
  );
}
