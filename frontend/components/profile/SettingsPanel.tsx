"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import ThemeToggle from "@/components/ThemeToggle";

function LockIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <rect x="3" y="11" width="18" height="11" rx="2" />
      <path d="M7 11V7a5 5 0 0 1 10 0v4" />
    </svg>
  );
}

/** Account, connection, theme and sign-out.
 *
 * This used to be a gear pinned over the page with `fixed`, and it existed
 * only on the Análisis tab: the one place holding "Cerrar sesión" was a
 * floating button that also sat on top of the cards underneath, covering the
 * "+" of the list it overlapped. It is a plain panel now, on its own Ajustes
 * tab, so nothing it contains is hidden behind an icon or on top of
 * something else. */
export default function SettingsPanel() {
  const { user, logout } = useAuth();
  const router = useRouter();
  // Read straight from the WebView's own address bar state — there's no
  // browser padlock to glance at inside a Capacitor app, so this is the
  // only way to confirm the connection is actually HTTPS and not
  // localhost/cleartext. Computed on mount (window isn't available during
  // SSR), not from an env var, so it reflects what's really loaded.
  const [connection, setConnection] = useState<{ secure: boolean; host: string } | null>(null);

  useEffect(() => {
    setConnection({
      secure: window.location.protocol === "https:",
      host: window.location.host,
    });
  }, []);

  function handleLogout() {
    logout();
    router.replace("/login");
  }

  return (
    <section className="space-y-4 rounded-2xl bg-white p-5 shadow-sm ring-1 ring-gray-100 dark:bg-gray-900 dark:ring-gray-800">
      <div>
        <h2 className="font-semibold text-gray-900 dark:text-gray-100">Ajustes</h2>
        <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
          Tu cuenta, el tema de la app y el diagnóstico técnico.
        </p>
      </div>

      <div className="flex items-center justify-between gap-3 rounded-xl bg-gray-50 px-3 py-2.5 dark:bg-gray-800/60">
        <div className="min-w-0">
          <p className="text-sm font-medium text-gray-700 dark:text-gray-300">Cuenta</p>
          <p className="truncate text-xs text-gray-500 dark:text-gray-400">{user?.email}</p>
        </div>
        {user && (
          <span
            className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-semibold ${
              user.email_verified
                ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300"
                : "bg-amber-50 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300"
            }`}
          >
            {user.email_verified ? "Verificada" : "Sin verificar"}
          </span>
        )}
      </div>

      {connection && (
        <div className="flex items-center gap-2 rounded-xl bg-gray-50 px-3 py-2.5 dark:bg-gray-800/60">
          <LockIcon
            className={`h-4 w-4 shrink-0 ${
              connection.secure
                ? "text-emerald-600 dark:text-emerald-400"
                : "text-rose-600 dark:text-rose-400"
            }`}
          />
          <div className="min-w-0">
            <p
              className={`text-xs font-semibold ${
                connection.secure
                  ? "text-emerald-700 dark:text-emerald-400"
                  : "text-rose-700 dark:text-rose-400"
              }`}
            >
              {connection.secure ? "Conexión segura (HTTPS)" : "Conexión sin cifrar"}
            </p>
            <p className="truncate text-[11px] text-gray-500 dark:text-gray-400">{connection.host}</p>
          </div>
        </div>
      )}

      <div className="flex items-center justify-between gap-3">
        <p className="text-sm font-medium text-gray-700 dark:text-gray-300">Tema</p>
        <ThemeToggle />
      </div>

      <button
        type="button"
        onClick={handleLogout}
        className="w-full rounded-xl border border-rose-200 px-3 py-2.5 text-sm font-semibold text-rose-600 hover:bg-rose-50 dark:border-rose-900/50 dark:text-rose-400 dark:hover:bg-rose-900/20"
      >
        Cerrar sesión
      </button>
    </section>
  );
}
