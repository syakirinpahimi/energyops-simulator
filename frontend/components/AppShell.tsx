"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { useEffect } from "react";
import { useAuth } from "@/components/providers/AuthProvider";
import { NAV_ITEMS, can } from "@/lib/permissions";
import { RoleBadge } from "@/components/RoleBadge";
import clsx from "clsx";

interface Props {
  children: React.ReactNode;
}

export function AppShell({ children }: Props) {
  const { user, signOut, hydrated, setRoleForDemo } = useAuth();
  const router = useRouter();
  const path = usePathname();
  const useMocks = process.env.NEXT_PUBLIC_USE_MOCKS === "1";

  useEffect(() => {
    if (hydrated && !user && path !== "/login") {
      router.replace("/login");
    }
  }, [hydrated, user, path, router]);

  if (!hydrated) {
    return (
      <div className="flex min-h-screen items-center justify-center text-steel-400">
        Loading…
      </div>
    );
  }
  if (!user) return <>{children}</>;

  const visibleNav = NAV_ITEMS.filter((n) => can(user.role, n.action));

  return (
    <div className="flex min-h-screen flex-col bg-steel-950 text-steel-100">
      <header className="flex h-12 shrink-0 items-center justify-between border-b border-steel-700 bg-steel-900 px-4">
        <div className="flex items-center gap-4">
          <Link href="/dashboard" className="flex items-center gap-2">
            <Logo />
            <span className="font-mono text-sm uppercase tracking-[0.18em] text-steel-100">
              EnergyOps
            </span>
            <span className="hidden text-[11px] uppercase tracking-widest text-steel-500 sm:inline">
              · industrial
            </span>
          </Link>
          <nav className="ml-4 hidden items-center gap-0.5 md:flex">
            {visibleNav.map((n) => (
              <Link
                key={n.href}
                href={n.href}
                className={clsx(
                  "rounded-sm px-3 py-1.5 text-sm",
                  path?.startsWith(n.href)
                    ? "bg-steel-700 text-accent"
                    : "text-steel-300 hover:bg-steel-800 hover:text-steel-100"
                )}
              >
                {n.label}
              </Link>
            ))}
          </nav>
        </div>
        <div className="flex items-center gap-3">
          {useMocks && (
            <select
              value={user.role}
              onChange={(e) => setRoleForDemo(e.target.value as never)}
              title="Demo: switch role (mock mode only)"
              className="rounded-sm border border-steel-600 bg-steel-800 px-2 py-1 font-mono text-[11px] uppercase tracking-widest text-steel-100"
            >
              <option value="operator">operator</option>
              <option value="engineer">engineer</option>
              <option value="manager">manager</option>
              <option value="admin">admin</option>
            </select>
          )}
          <div className="hidden items-center gap-2 sm:flex">
            <RoleBadge role={user.role} />
            <span className="text-sm text-steel-200">{user.name}</span>
          </div>
          <button
            type="button"
            onClick={() => {
              signOut();
              router.replace("/login");
            }}
            className="rounded-sm border border-steel-600 px-2 py-1 text-xs text-steel-300 hover:bg-steel-800"
          >
            Sign out
          </button>
        </div>
      </header>
      <main className="flex-1">{children}</main>
      <footer className="flex h-7 items-center justify-between border-t border-steel-800 bg-steel-900 px-4 font-mono text-[11px] text-steel-500">
        <span>energyops · v0.1.0 · MVP</span>
        <span>{useMocks ? "MOCK MODE" : "LIVE"}</span>
      </footer>
    </div>
  );
}

function Logo() {
  // Original mark: a stylised sine wave inside a hex frame.
  return (
    <svg
      viewBox="0 0 24 24"
      width={22}
      height={22}
      fill="none"
      stroke="currentColor"
      strokeWidth={1.5}
      className="text-accent"
      aria-hidden
    >
      <polygon points="12 2 21 7 21 17 12 22 3 17 3 7" />
      <path d="M5 13c2-3 3-3 4 0s2 3 3 0 2-3 3 0 2 3 3 0" strokeLinecap="round" />
    </svg>
  );
}
