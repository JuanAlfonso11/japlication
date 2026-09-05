"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import VerificationBanner from "@/components/VerificationBanner";
import ThemeToggle from "@/components/ThemeToggle";
import { applicationsApi } from "@/lib/api";

const NAV_ITEMS = [
  { href: "/", label: "Inicio", icon: HomeIcon },
  { href: "/discover", label: "Buscar", icon: DiscoverIcon },
  { href: "/jobs/import", label: "Importar", icon: ImportIcon },
  { href: "/applications", label: "Pipeline", icon: PipelineIcon },
  { href: "/profile", label: "Perfil", icon: ProfileIcon },
];

// How often to re-check the stale-applications count while the app stays
// open — matches UpdateChecker.tsx's own recheck interval, no need for
// this cosmetic badge to poll any more aggressively than that.
const STALE_COUNT_RECHECK_MS = 30 * 60 * 1000;

function NavBadge({ count }: { count: number }) {
  if (count <= 0) return null;
  return (
    <span className="absolute -right-1 -top-1 flex h-4 min-w-[16px] items-center justify-center rounded-full bg-rose-500 px-1 text-[10px] font-bold leading-none text-white">
      {count > 9 ? "9+" : count}
    </span>
  );
}

export default function NavShell({ children }: { children: React.ReactNode }) {
  const pathname = usePathname();
  const { user, token } = useAuth();
  const [staleCount, setStaleCount] = useState(0);

  useEffect(() => {
    if (!token) return;
    let cancelled = false;
    function load() {
      applicationsApi
        .staleCount()
        .then((res) => {
          if (!cancelled) setStaleCount(res.count);
        })
        .catch(() => {
          // Cosmetic feature — a failed fetch just means no badge shows.
        });
    }
    load();
    const interval = setInterval(load, STALE_COUNT_RECHECK_MS);
    return () => {
      cancelled = true;
      clearInterval(interval);
    };
  }, [token]);

  // /verify-email included here too so the "check your email" gate right
  // after signup reads as a standalone step, not just another app page.
  const isAuthScreen =
    pathname === "/login" || pathname === "/register" || pathname === "/verify-email";

  if (isAuthScreen || !token) {
    return <div className="min-h-dvh bg-gray-50 dark:bg-gray-950">{children}</div>;
  }

  return (
    <div className="min-h-dvh bg-gray-50 dark:bg-gray-950">
      {/* Top nav (desktop) */}
      <header className="sticky top-0 z-40 hidden border-b border-gray-200 bg-white/90 backdrop-blur md:block dark:border-gray-800 dark:bg-gray-900/90">
        <div className="mx-auto flex max-w-5xl items-center justify-between px-6 py-3">
          <Link href="/" className="flex items-center gap-2 font-semibold text-gray-900 dark:text-gray-100">
            <img src="/icons/icon-192.png" alt="" className="h-8 w-8" />
            JobPilot
          </Link>
          <nav className="flex items-center gap-1">
            {NAV_ITEMS.map((item) => {
              const active =
                item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
              return (
                <Link
                  key={item.href}
                  href={item.href}
                  className={`relative rounded-lg px-3 py-2 text-sm font-medium transition-colors ${
                    active
                      ? "bg-brand-50 text-brand-700 dark:bg-brand-900/40 dark:text-brand-300"
                      : "text-gray-600 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-100"
                  }`}
                >
                  {item.label}
                  {item.href === "/applications" && <NavBadge count={staleCount} />}
                </Link>
              );
            })}
          </nav>
          <div className="flex items-center gap-3">
            {user && (
              <span className="hidden text-sm text-gray-500 lg:inline dark:text-gray-400">{user.full_name}</span>
            )}
            <ThemeToggle />
          </div>
        </div>
      </header>

      {/* Mobile top bar — padding-top covers the status bar (battery/clock)
          area on the Android app, which renders edge-to-edge by default. */}
      <header
        className="sticky top-0 z-40 flex items-center justify-between border-b border-gray-200 bg-white/90 px-4 pb-3 backdrop-blur md:hidden dark:border-gray-800 dark:bg-gray-900/90"
        style={{ paddingTop: "calc(env(safe-area-inset-top) + 0.75rem)" }}
      >
        <Link href="/" className="flex items-center gap-2 font-semibold text-gray-900 dark:text-gray-100">
          <img src="/icons/icon-192.png" alt="" className="h-7 w-7" />
          JobPilot
        </Link>
        <ThemeToggle compact />
      </header>

      <main className="mx-auto max-w-5xl px-4 pb-24 pt-4 md:px-6 md:pb-10 md:pt-6">
        <VerificationBanner />
        {children}
      </main>

      {/* Bottom tab bar (mobile) */}
      <nav
        className="fixed inset-x-0 bottom-0 z-40 border-t border-gray-200 bg-white/95 backdrop-blur md:hidden dark:border-gray-800 dark:bg-gray-900/95"
        style={{ paddingBottom: "env(safe-area-inset-bottom)" }}
      >
        <div className="grid grid-cols-5">
          {NAV_ITEMS.map((item) => {
            const active =
              item.href === "/" ? pathname === "/" : pathname.startsWith(item.href);
            const Icon = item.icon;
            return (
              <Link
                key={item.href}
                href={item.href}
                className={`flex min-h-[56px] flex-col items-center justify-center gap-0.5 text-[11px] font-medium ${
                  active ? "text-brand-600 dark:text-brand-400" : "text-gray-500 dark:text-gray-400"
                }`}
              >
                {/* Same filled-pill treatment as the desktop nav's active
                    link (bg-brand-50), so "active" reads identically on
                    both — mobile just applies it to the icon instead of
                    the whole row, since there's no room for a label pill
                    in a 5-column bottom bar. */}
                <span
                  className={`relative flex items-center justify-center rounded-full px-3 py-1 transition-colors ${
                    active ? "bg-brand-50 dark:bg-brand-900/40" : ""
                  }`}
                >
                  <Icon active={active} />
                  {item.href === "/applications" && <NavBadge count={staleCount} />}
                </span>
                {item.label}
              </Link>
            );
          })}
        </div>
      </nav>
    </div>
  );
}

function HomeIcon({ active }: { active: boolean }) {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={active ? 2.2 : 1.8} strokeLinecap="round" strokeLinejoin="round">
      <path d="M3 11.5 12 4l9 7.5" />
      <path d="M5 10v9a1 1 0 0 0 1 1h4v-6h4v6h4a1 1 0 0 0 1-1v-9" />
    </svg>
  );
}

function DiscoverIcon({ active }: { active: boolean }) {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={active ? 2.2 : 1.8} strokeLinecap="round" strokeLinejoin="round">
      <circle cx="11" cy="11" r="7" />
      <path d="m20 20-4.3-4.3" />
    </svg>
  );
}

function ImportIcon({ active }: { active: boolean }) {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={active ? 2.2 : 1.8} strokeLinecap="round" strokeLinejoin="round">
      <path d="M12 3v12" />
      <path d="m7 10 5 5 5-5" />
      <path d="M4 19h16" />
    </svg>
  );
}

function PipelineIcon({ active }: { active: boolean }) {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={active ? 2.2 : 1.8} strokeLinecap="round" strokeLinejoin="round">
      <rect x="3" y="4" width="18" height="4" rx="1" />
      <rect x="3" y="10" width="12" height="4" rx="1" />
      <rect x="3" y="16" width="8" height="4" rx="1" />
    </svg>
  );
}

function ProfileIcon({ active }: { active: boolean }) {
  return (
    <svg width="22" height="22" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth={active ? 2.2 : 1.8} strokeLinecap="round" strokeLinejoin="round">
      <circle cx="12" cy="8" r="3.5" />
      <path d="M4.5 20c1.5-3.5 5-5 7.5-5s6 1.5 7.5 5" />
    </svg>
  );
}
