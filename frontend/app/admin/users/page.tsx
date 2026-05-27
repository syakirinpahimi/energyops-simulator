"use client";

import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { User } from "@/lib/types";
import { RoleBadge } from "@/components/RoleBadge";
import { useAuth } from "@/components/providers/AuthProvider";
import { can } from "@/lib/permissions";

export default function AdminUsersPage() {
  const { user } = useAuth();
  const [users, setUsers] = useState<User[]>([]);

  useEffect(() => {
    let cancel = false;
    api<User[]>("/api/v1/users").then((u) => !cancel && setUsers(u));
    return () => {
      cancel = true;
    };
  }, []);

  if (!can(user?.role, "user.manage")) {
    return (
      <div className="grid-bg flex min-h-[calc(100vh-76px)] items-center justify-center">
        <div className="panel max-w-md p-6 text-center">
          <h1 className="text-lg font-semibold text-steel-50">Admin only</h1>
          <p className="mt-2 text-sm text-steel-400">
            Sign in with the admin role to manage users.
          </p>
        </div>
      </div>
    );
  }

  return (
    <div className="grid-bg min-h-[calc(100vh-76px)] space-y-4 p-4">
      <div>
        <h1 className="text-lg font-semibold text-steel-50">Users</h1>
        <p className="text-xs text-steel-400">
          Manage roles. Backend mutations are wired through{" "}
          <code className="font-mono">/api/v1/users</code> · TODO(future) edit forms.
        </p>
      </div>

      <div className="overflow-hidden rounded-md border border-steel-700 bg-steel-800 shadow-panel">
        <table className="w-full text-sm">
          <thead className="border-b border-steel-700 bg-steel-900/50 text-left text-[11px] uppercase tracking-wider text-steel-300">
            <tr>
              <th className="px-3 py-2 font-medium">Name</th>
              <th className="px-3 py-2 font-medium">Email</th>
              <th className="px-3 py-2 font-medium">Role</th>
              <th className="px-3 py-2 font-medium">Created</th>
            </tr>
          </thead>
          <tbody>
            {users.map((u) => (
              <tr key={u.id} className="border-b border-steel-700/60 last:border-0 hover:bg-steel-700/30">
                <td className="px-3 py-2 text-steel-100">{u.name}</td>
                <td className="px-3 py-2 font-mono text-steel-200">{u.email}</td>
                <td className="px-3 py-2">
                  <RoleBadge role={u.role} />
                </td>
                <td className="px-3 py-2 text-steel-300">
                  {new Date(u.created_at).toLocaleDateString()}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </div>
  );
}
