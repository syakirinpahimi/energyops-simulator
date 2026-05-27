import clsx from "clsx";
import type { Role } from "@/lib/types";

const STYLES: Record<Role, string> = {
  admin: "border-accent/40 bg-accent/10 text-accent",
  manager: "border-signal-info/40 bg-signal-info/10 text-signal-info",
  engineer: "border-emerald-500/40 bg-emerald-500/10 text-emerald-300",
  operator: "border-steel-500/40 bg-steel-700 text-steel-100"
};

export function RoleBadge({ role, className }: { role: Role; className?: string }) {
  return (
    <span
      className={clsx(
        "inline-flex items-center rounded-sm border px-2 py-0.5 font-mono text-[11px] uppercase tracking-widest",
        STYLES[role],
        className
      )}
    >
      {role}
    </span>
  );
}
