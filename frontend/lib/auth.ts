"use client";

import { useEffect, useState } from "react";
import { api, getToken, setToken, ApiError } from "@/lib/api";
import type { Role, User } from "@/lib/types";

const USER_KEY = "energyops.user";

export interface StoredUser {
  id: string;
  email: string;
  name: string;
  role: Role;
  company_id: string;
}

export { getToken, setToken };

export function clearToken(): void {
  setToken(null);
  if (typeof window !== "undefined") {
    try {
      window.localStorage.removeItem(USER_KEY);
    } catch {
      /* ignore */
    }
  }
}

export function getStoredUser(): StoredUser | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(USER_KEY);
    return raw ? (JSON.parse(raw) as StoredUser) : null;
  } catch {
    return null;
  }
}

export function setStoredUser(user: StoredUser): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(USER_KEY, JSON.stringify(user));
  } catch {
    /* ignore */
  }
}

/** Tiny client-side auth helper. Holds the user in state, refreshes from /auth/me. */
export function useUser(): { user: User | null; loading: boolean; reload: () => void } {
  const [user, setUser] = useState<User | null>(null);
  const [loading, setLoading] = useState<boolean>(true);

  const reload = () => {
    if (!getToken()) {
      setUser(null);
      setLoading(false);
      return;
    }
    setLoading(true);
    api<User>("/auth/me")
      .then((u) => setUser(u))
      .catch((err) => {
        if (err instanceof ApiError && err.status === 401) setToken(null);
        setUser(null);
      })
      .finally(() => setLoading(false));
  };

  useEffect(() => {
    reload();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return { user, loading, reload };
}

const ROLE_ORDER: Record<User["role"], number> = {
  operator: 0,
  engineer: 1,
  manager: 2,
  admin: 3,
};

export function roleAtLeast(user: User | null, level: User["role"]): boolean {
  if (!user) return false;
  return ROLE_ORDER[user.role] >= ROLE_ORDER[level];
}

export function canAcknowledgeAlarm(user: User | null): boolean {
  return roleAtLeast(user, "operator");
}

export function canResolveAlarm(user: User | null): boolean {
  return roleAtLeast(user, "engineer");
}

export function canViewAudit(user: User | null): boolean {
  return roleAtLeast(user, "engineer");
}

export function canGenerateReports(user: User | null): boolean {
  return roleAtLeast(user, "manager");
}
