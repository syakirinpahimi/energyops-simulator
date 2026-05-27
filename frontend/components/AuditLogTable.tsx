import type { AuditEntry } from "@/lib/types";
import { fmtClock } from "@/lib/format";

interface Props {
  entries: AuditEntry[];
}

export function AuditLogTable({ entries }: Props) {
  return (
    <div className="overflow-hidden rounded-md border border-steel-700 bg-steel-800 shadow-panel">
      <table className="w-full text-sm">
        <thead className="border-b border-steel-700 bg-steel-900/50 text-left text-[11px] uppercase tracking-wider text-steel-300">
          <tr>
            <th className="px-3 py-2 font-medium">Time</th>
            <th className="px-3 py-2 font-medium">Actor</th>
            <th className="px-3 py-2 font-medium">Action</th>
            <th className="px-3 py-2 font-medium">Target</th>
            <th className="px-3 py-2 font-medium">Note</th>
          </tr>
        </thead>
        <tbody>
          {entries.length === 0 && (
            <tr>
              <td colSpan={5} className="px-3 py-6 text-center text-steel-400">
                No audit entries.
              </td>
            </tr>
          )}
          {entries.map((e) => (
            <tr
              key={e.id}
              className="border-b border-steel-700/60 last:border-0 hover:bg-steel-700/30"
            >
              <td className="px-3 py-2 font-mono text-steel-200">
                <div>{fmtClock(e.ts)}</div>
                <div className="text-[11px] text-steel-500">
                  {new Date(e.ts).toLocaleDateString()}
                </div>
              </td>
              <td className="px-3 py-2 text-steel-100">{e.actor_email}</td>
              <td className="px-3 py-2 font-mono text-xs text-accent">{e.action}</td>
              <td className="px-3 py-2 text-steel-300">
                <span className="font-mono text-[11px] text-steel-500">{e.target_type}:</span>{" "}
                <span className="text-steel-200">{e.target_id}</span>
              </td>
              <td className="px-3 py-2 text-steel-300">
                {(e.metadata && (e.metadata as { note?: string }).note) ?? "—"}
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}
