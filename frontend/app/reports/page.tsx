"use client";

import { useEffect, useState } from "react";
import { api, downloadFile } from "@/lib/api";
import type { ReportSummary, Site } from "@/lib/types";
import { ReportExportPanel } from "@/components/ReportExportPanel";
import { useAuth } from "@/components/providers/AuthProvider";
import { can } from "@/lib/permissions";

export default function ReportsPage() {
  const { user } = useAuth();
  const [sites, setSites] = useState<Site[]>([]);
  const [reports, setReports] = useState<ReportSummary[]>([]);

  useEffect(() => {
    let cancel = false;
    api<Site[]>("/api/v1/sites").then((s) => !cancel && setSites(s));
    api<ReportSummary[]>("/api/v1/reports").then((r) => !cancel && setReports(r));
    return () => {
      cancel = true;
    };
  }, []);

  const canGen = can(user?.role, "report.generate");

  async function generate(params: {
    site_id: string;
    from: string;
    to: string;
    format: "pdf" | "csv";
  }) {
    const r = await api<ReportSummary>("/api/v1/reports/energy", {
      method: "POST",
      body: params
    });
    setReports((prev) => [r, ...prev]);
    return r;
  }

  async function download(id: string) {
    await downloadFile(`/api/v1/reports/${id}/download`, undefined, `report-${id}.bin`);
  }

  return (
    <div className="grid-bg min-h-[calc(100vh-76px)] space-y-4 p-4">
      <div>
        <h1 className="text-lg font-semibold text-steel-50">Reports</h1>
        <p className="text-xs text-steel-400">
          Generate per-site energy reports. Records are written to the audit log.
        </p>
      </div>

      <ReportExportPanel
        sites={sites}
        recentReports={reports}
        canGenerate={canGen}
        onGenerate={generate}
        onDownload={download}
      />
    </div>
  );
}
