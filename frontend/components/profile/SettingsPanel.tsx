"use client";

import { useEffect, useRef, useState } from "react";
import { useRouter } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import ThemeToggle from "@/components/ThemeToggle";

function GearIcon({ className }: { className?: string }) {
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
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 1 1-2.83 2.83l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-4 0v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 1 1-2.83-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1 0-4h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 1 1 2.83-2.83l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 4 0v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 1 1 2.83 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 0 4h-.09a1.65 1.65 0 0 0-1.51 1Z" />
    </svg>
  );
}

/** Small gear icon, anchored to a corner — opens a compact popover instead
 * of an inline card, so it doesn't take up space in the page flow. */
export default function SettingsPanel() {
  const { user, logout } = useAuth();
  const router = useRouter();
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function handleClickOutside(e: MouseEvent) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [open]);

  function handleLogout() {
    logout();
    router.replace("/login");
  }

  return (
    <div
      ref={wrapperRef}
      className="fixed right-3 z-30"
      style={{ top: "calc(env(safe-area-inset-top) + 3.75rem)" }}
    >
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-label="Configuración"
        aria-expanded={open}
        className="flex h-10 w-10 items-center justify-center rounded-full bg-white text-gray-400 shadow-sm ring-1 ring-gray-100 hover:bg-gray-100 hover:text-gray-600 dark:bg-gray-900 dark:text-gray-500 dark:ring-gray-800 dark:hover:bg-gray-800 dark:hover:text-gray-300"
      >
        <GearIcon className="h-5 w-5" />
      </button>

      {open && (
        <div className="absolute right-0 top-12 w-64 space-y-4 rounded-xl bg-white p-4 shadow-lg ring-1 ring-gray-100 dark:bg-gray-900 dark:ring-gray-800">
          <div className="flex items-center justify-between gap-3">
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

          <div className="flex items-center justify-between gap-3">
            <p className="text-sm font-medium text-gray-700 dark:text-gray-300">Tema</p>
            <ThemeToggle />
          </div>

          <button
            type="button"
            onClick={handleLogout}
            className="w-full rounded-lg border border-rose-200 px-3 py-2 text-sm font-semibold text-rose-600 hover:bg-rose-50 dark:border-rose-900/50 dark:text-rose-400 dark:hover:bg-rose-900/20"
          >
            Cerrar sesión
          </button>
        </div>
      )}
    </div>
  );
}
