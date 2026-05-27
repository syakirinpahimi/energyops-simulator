"use client";

import { createContext, useCallback, useContext, useEffect, useMemo, useState } from "react";
import type { Role, User } from "@/lib/types";
import { clearToken, getStoredUser, setStoredUser, setToken, type StoredUser } from "@/lib/auth";

interface AuthCtx {
  user: StoredUser | null;
  setSession: (token: string, user: User) => void;
  signOut: () => void;
  hydrated: boolean;
  setRoleForDemo: (role: Role) => void;
}

const Ctx = createContext<AuthCtx | null>(null);

export function AuthProvider({ children }: { children: React.ReactNode }) {
  const [user, setUser] = useState<StoredUser | null>(null);
  const [hydrated, setHydrated] = useState(false);

  useEffect(() => {
    setUser(getStoredUser());
    setHydrated(true);
  }, []);

  const setSession = useCallback((token: string, u: User) => {
    setToken(token);
    const stored: StoredUser = {
      id: u.id,
      email: u.email,
      name: u.name,
      role: u.role,
      company_id: u.company_id
    };
    setStoredUser(stored);
    setUser(stored);
  }, []);

  const signOut = useCallback(() => {
    clearToken();
    setUser(null);
  }, []);

  // Demo helper so a single mock login can be flipped between roles in the UI
  // without re-entering credentials. Stripped out when mocks are off.
  const setRoleForDemo = useCallback((role: Role) => {
    if (!user) return;
    const next = { ...user, role };
    setStoredUser(next);
    setUser(next);
  }, [user]);

  const value = useMemo(
    () => ({ user, setSession, signOut, hydrated, setRoleForDemo }),
    [user, setSession, signOut, hydrated, setRoleForDemo]
  );

  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useAuth(): AuthCtx {
  const v = useContext(Ctx);
  if (!v) throw new Error("useAuth must be used inside <AuthProvider>");
  return v;
}
