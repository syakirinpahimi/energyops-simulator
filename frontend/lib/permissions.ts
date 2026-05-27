import type { Role } from "./types";

// Mirror of docs/API_CONTRACT.md § Role permissions.
export type Action =
  | "view.dashboards"
  | "alarm.ack"
  | "alarm.resolve"
  | "asset.edit"
  | "report.generate"
  | "user.manage"
  | "audit.view"
  | "hierarchy.manage";

const matrix: Record<Action, Role[]> = {
  "view.dashboards": ["operator", "engineer", "manager", "admin"],
  "alarm.ack": ["operator", "engineer", "manager", "admin"],
  "alarm.resolve": ["engineer", "manager", "admin"],
  "asset.edit": ["engineer", "manager", "admin"],
  "report.generate": ["manager", "admin"],
  "user.manage": ["admin"],
  "audit.view": ["engineer", "manager", "admin"],
  "hierarchy.manage": ["manager", "admin"]
};

export function can(role: Role | undefined | null, action: Action): boolean {
  if (!role) return false;
  return matrix[action].includes(role);
}

export interface NavItem {
  href: string;
  label: string;
  action: Action;
}

// Nav items visible only when can(role, item.action) returns true.
export const NAV_ITEMS: NavItem[] = [
  { href: "/dashboard", label: "Dashboard", action: "view.dashboards" },
  { href: "/sites", label: "Sites", action: "view.dashboards" },
  { href: "/alarms", label: "Alarms", action: "alarm.ack" },
  { href: "/reports", label: "Reports", action: "report.generate" },
  { href: "/audit-log", label: "Audit Log", action: "audit.view" },
  { href: "/admin/users", label: "Admin", action: "user.manage" }
];
