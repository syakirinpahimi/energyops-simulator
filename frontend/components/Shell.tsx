"use client";

import Link from "next/link";
import { usePathname, useRouter } from "next/navigation";
import { setToken } from "@/lib/api";
import { canViewAudit, useUser } from "@/lib/auth";

interface NavLink {
  href: string;
  label: string;
  show: (role: string) => boolean;
}

const NAV: NavLink[] = [
  { href: "/alarms", label: "Alarms", show: () => true },
  { href: "/reports", label: "Reports", show: () => true },
  { href: "/audit", label: "Audit log", show: (role) => role === "engineer" || role === "manager" || role === "admin" },
];

export function Shell({ children }: { children: React.ReactNode }) {
  const { user, loading } = useUser();
  const pathname = usePathname();
  const router = useRouter();

  if (loading) {
    return <div className="flex min-h-screen items-center justify-center text-muted">Loading...</div>;
  }
  if (!user) {
    if (typeof window !== "undefined" && pathname !== "/login") {
      router.replace("/login");
    }
    return <>{children}</>;
  }

  const onLogout = () => {
    setToken(null);
    router.replace("/login");
  };

  return (
    <div className="min-h-screen">
      <header className="border-b border-edge bg-panel">
        <div className="mx-auto flex max-w-6xl items-center justify-between px-4 py-3">
          <div className="flex items-center gap-6">
            <Link href="/alarms" className="text-base font-semibold tracking-tight text-cyan-300">
              EnergyOps
            </Link>
            <nav className="flex items-center gap-1">
              {NAV.filter((n) => n.show(user.role)).map((link) => {
                const active = pathname === link.href || pathname?.startsWith(`${link.href}/`);
                return (
                  <Link
                    key={link.href}
                    href={link.href}
                    className={`rounded px-3 py-1.5 text-sm ${
                      active ? "bg-edge text-slate-100" : "text-slate-300 hover:bg-edge/60"
                    }`}
                  >
                    {link.label}
                  </Link>
                );
              })}
            </nav>
          </div>
          <div className="flex items-center gap-3 text-sm text-muted">
            <div className="flex flex-col items-end">
              <span className="text-slate-200">{user.name}</span>
              <span className="text-xs uppercase tracking-wide">{user.role}</span>
            </div>
            <button onClick={onLogout} className="btn">
              Logout
            </button>
          </div>
        </div>
      </header>
      <main className="mx-auto max-w-6xl px-4 py-6">{children}</main>
    </div>
  );
}

export function PageHeader({ title, subtitle, right }: { title: string; subtitle?: string; right?: React.ReactNode }) {
  return (
    <div className="mb-4 flex items-end justify-between gap-3">
      <div>
        <h1 className="text-xl font-semibold tracking-tight text-slate-100">{title}</h1>
        {subtitle ? <p className="text-sm text-muted">{subtitle}</p> : null}
      </div>
      {right ? <div>{right}</div> : null}
    </div>
  );
}

export function Section({ title, children }: { title?: string; children: React.ReactNode }) {
  return (
    <section className="card mb-4">
      {title ? <h2 className="mb-3 text-sm font-semibold uppercase tracking-wide text-muted">{title}</h2> : null}
      {children}
    </section>
  );
}

export function ErrorBanner({ message }: { message: string }) {
  return (
    <div className="mb-3 rounded-md border border-red-500/40 bg-red-500/10 px-3 py-2 text-sm text-red-200">
      {message}
    </div>
  );
}

export { canViewAudit };
