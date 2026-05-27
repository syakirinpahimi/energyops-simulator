"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { api, ApiRequestError } from "@/lib/api";
import type { LoginResponse } from "@/lib/types";
import { useAuth } from "@/components/providers/AuthProvider";

const DEMO_USERS = [
  { email: "operator@energyops.local", password: "Operator#12345", role: "operator" },
  { email: "engineer@energyops.local", password: "Engineer#12345", role: "engineer" },
  { email: "manager@energyops.local", password: "Manager#12345", role: "manager" },
  { email: "admin@energyops.local", password: "Admin#12345", role: "admin" }
];

export default function LoginPage() {
  const { setSession, user, hydrated } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("operator@energyops.local");
  const [password, setPassword] = useState("Operator#12345");
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const useMocks = process.env.NEXT_PUBLIC_USE_MOCKS === "1";

  useEffect(() => {
    if (hydrated && user) router.replace("/dashboard");
  }, [hydrated, user, router]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setBusy(true);
    try {
      const resp = await api<LoginResponse>("/api/v1/auth/login", {
        method: "POST",
        unauth: true,
        body: { email, password }
      });
      setSession(resp.access_token, resp.user);
      router.replace("/dashboard");
    } catch (err) {
      const msg = err instanceof ApiRequestError ? err.message : "Login failed";
      setError(msg);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="grid-bg flex min-h-screen items-center justify-center bg-steel-950 px-4">
      <div className="w-full max-w-md panel p-6">
        <div className="mb-5 flex items-center gap-3 border-b border-steel-700 pb-4">
          <svg
            viewBox="0 0 24 24"
            width={28}
            height={28}
            fill="none"
            stroke="currentColor"
            strokeWidth={1.5}
            className="text-accent"
            aria-hidden
          >
            <polygon points="12 2 21 7 21 17 12 22 3 17 3 7" />
            <path d="M5 13c2-3 3-3 4 0s2 3 3 0 2-3 3 0 2 3 3 0" strokeLinecap="round" />
          </svg>
          <div>
            <div className="font-mono text-sm uppercase tracking-[0.18em]">EnergyOps</div>
            <div className="text-xs text-steel-400">Industrial Operations Console</div>
          </div>
        </div>

        <form onSubmit={submit} className="space-y-3">
          <label className="block">
            <span className="mb-1 block text-[11px] uppercase tracking-wider text-steel-300">
              Email
            </span>
            <input
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-sm border border-steel-600 bg-steel-900 px-3 py-2 font-mono text-sm focus:border-accent focus:outline-none"
              autoComplete="username"
              required
            />
          </label>
          <label className="block">
            <span className="mb-1 block text-[11px] uppercase tracking-wider text-steel-300">
              Password
            </span>
            <input
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-sm border border-steel-600 bg-steel-900 px-3 py-2 font-mono text-sm focus:border-accent focus:outline-none"
              autoComplete="current-password"
              required
            />
          </label>

          {error && (
            <div className="rounded-sm border border-signal-fault/40 bg-signal-fault/10 px-3 py-2 text-xs text-signal-fault">
              {error}
            </div>
          )}

          <button
            type="submit"
            disabled={busy}
            className="w-full rounded-sm border border-accent bg-accent/10 px-3 py-2 text-sm font-medium uppercase tracking-widest text-accent hover:bg-accent/20 disabled:opacity-50"
          >
            {busy ? "Signing in…" : "Sign in"}
          </button>
        </form>

        {useMocks && (
          <div className="mt-5 border-t border-steel-700 pt-4">
            <div className="mb-2 text-[11px] uppercase tracking-wider text-steel-400">
              Mock Mode · quick login
            </div>
            <div className="grid grid-cols-2 gap-2">
              {DEMO_USERS.map((u) => (
                <button
                  key={u.email}
                  type="button"
                  onClick={() => {
                    setEmail(u.email);
                    setPassword(u.password);
                  }}
                  className="rounded-sm border border-steel-600 px-2 py-1.5 text-xs text-steel-200 hover:bg-steel-700"
                >
                  {u.role}
                </button>
              ))}
            </div>
          </div>
        )}

        <div className="mt-5 border-t border-steel-700 pt-4">
          <div className="mb-2 text-[11px] uppercase tracking-wider text-steel-400">
            Demo accounts · click to fill
          </div>
          <div className="grid grid-cols-2 gap-2">
            {DEMO_USERS.map((u) => (
              <button
                key={`hint-${u.email}`}
                type="button"
                onClick={() => {
                  setEmail(u.email);
                  setPassword(u.password);
                }}
                className="flex flex-col items-start rounded-sm border border-steel-600 px-2 py-1.5 text-left text-[11px] text-steel-200 hover:bg-steel-700"
              >
                <span className="font-mono uppercase tracking-wider text-accent">
                  {u.role}
                </span>
                <span className="font-mono text-steel-400">{u.email}</span>
              </button>
            ))}
          </div>
          <p className="mt-2 text-[11px] text-steel-500">
            Default passwords come from <code>.env.example</code>. Rotate
            them in <code>.env</code> before any real demo.
          </p>
        </div>

        <p className="mt-4 text-[11px] text-steel-500">
          Operator credentials log alarm acknowledgements to the audit log.
        </p>
      </div>
    </div>
  );
}
