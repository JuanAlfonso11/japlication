"use client";

import { useCallback, useEffect, useState } from "react";
import { ApiError, systemApi } from "@/lib/api";
import type { ErrorLogEntry } from "@/lib/types";

/** Everything that has failed recently, readable from the phone.
 *
 * The point is to make diagnosis possible without a laptop: backend
 * tracebacks used to live only in `docker compose logs`, and a crash in the
 * WebView left nothing at all. Both now land here, newest first, with the
 * short id the user was shown on screen so a report of "salió el código
 * a1b2c3" maps to an exact row.
 *
 * Collapsed by default — a panel that dumps stack traces at you every time
 * you open Perfil is a panel you stop reading. */

function relativeTime(iso: string): string {
  const then = new Date(iso).getTime();
  const seconds = Math.round((Date.now() - then) / 1000);
  if (seconds < 60) return "hace un momento";
  const minutes = Math.round(seconds / 60);
  if (minutes < 60) return `hace ${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `hace ${hours} h`;
  const days = Math.round(hours / 24);
  return `hace ${days} d`;
}

function ErrorRow({ entry }: { entry: ErrorLogEntry }) {
  const [open, setOpen] = useState(false);
  const isBackend = entry.source === "backend";

  return (
    <li className="rounded-xl bg-gray-50 dark:bg-gray-800/60">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        className="flex w-full items-start gap-2.5 p-3 text-left"
      >
        <span
          className={`mt-0.5 shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide ${
            isBackend
              ? "bg-brand-50 text-brand-700 dark:bg-brand-500/15 dark:text-brand-300"
              : "bg-accent-50 text-accent-700 dark:bg-accent-500/15 dark:text-accent-300"
          }`}
        >
          {isBackend ? "API" : "App"}
        </span>
        <span className="min-w-0 flex-1">
          <span className="block truncate text-[13px] font-semibold text-gray-900 dark:text-gray-100">
            {entry.kind ? `${entry.kind}: ` : ""}
            {entry.message}
          </span>
          <span className="mt-0.5 block truncate text-[11px] text-gray-500 dark:text-gray-400">
            {entry.method ? `${entry.method} ` : ""}
            {entry.path ?? entry.url ?? ""}
            {entry.status_code ? ` · ${entry.status_code}` : ""}
            {` · ${relativeTime(entry.created_at)}`}
          </span>
        </span>
        <svg
          aria-hidden="true"
          width="15"
          height="15"
          viewBox="0 0 24 24"
          fill="none"
          stroke="currentColor"
          strokeWidth="2.5"
          strokeLinecap="round"
          strokeLinejoin="round"
          className={`mt-1 shrink-0 text-gray-300 transition-transform dark:text-gray-600 ${
            open ? "rotate-180" : ""
          }`}
        >
          <path d="m6 9 6 6 6-6" />
        </svg>
      </button>

      {open && (
        <div className="border-t border-gray-200 px-3 pb-3 pt-2.5 dark:border-gray-700">
          <p className="mb-2 font-mono text-[11px] text-gray-400 dark:text-gray-400">
            id: {entry.request_id} · {new Date(entry.created_at).toLocaleString()}
          </p>
          {entry.stack ? (
            <pre className="max-h-64 overflow-auto rounded-lg bg-white p-2.5 font-mono text-[10px] leading-relaxed text-gray-700 dark:bg-gray-900 dark:text-gray-300">
              {entry.stack}
            </pre>
          ) : (
            <p className="text-[11px] text-gray-400 dark:text-gray-400">Sin traza disponible.</p>
          )}
          {entry.user_agent && (
            <p className="mt-2 break-words text-[10px] text-gray-400 dark:text-gray-400">
              {entry.user_agent}
            </p>
          )}
        </div>
      )}
    </li>
  );
}

export default function ErrorLogPanel() {
  const [entries, setEntries] = useState<ErrorLogEntry[] | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [expanded, setExpanded] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setEntries(await systemApi.errors({ limit: 50 }));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudieron cargar los errores.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (expanded && entries === null) load();
  }, [expanded, entries, load]);

  return (
    <section className="rounded-2xl bg-white p-5 shadow-soft ring-1 ring-gray-100 dark:bg-gray-900 dark:ring-gray-800">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="font-display font-bold text-gray-900 dark:text-gray-100">
            Errores recientes
          </h2>
          <p className="mt-0.5 text-xs leading-relaxed text-gray-500 dark:text-gray-400">
            Todo lo que ha fallado, del servidor y de la app, en un solo lugar.
          </p>
        </div>
        <div className="flex shrink-0 gap-2">
          {expanded && (
            <button
              type="button"
              onClick={load}
              disabled={loading}
              className="inline-flex min-h-[34px] items-center rounded-lg bg-white px-3 text-xs font-bold text-gray-600 ring-1 ring-inset ring-gray-200 transition-colors hover:bg-gray-50 disabled:opacity-60 dark:bg-gray-900 dark:text-gray-300 dark:ring-gray-700"
            >
              {loading ? "…" : "Actualizar"}
            </button>
          )}
          <button
            type="button"
            onClick={() => setExpanded((v) => !v)}
            className="inline-flex min-h-[34px] items-center rounded-lg bg-brand-600 px-3.5 text-xs font-bold text-white transition-colors hover:bg-brand-700 active:scale-95"
          >
            {expanded ? "Ocultar" : "Ver"}
          </button>
        </div>
      </div>

      {expanded && (
        <div className="mt-4">
          {error && <p className="text-sm text-rose-600 dark:text-rose-400">{error}</p>}
          {loading && entries === null && (
            <p className="text-sm text-gray-500 dark:text-gray-400">Cargando…</p>
          )}
          {entries !== null && entries.length === 0 && (
            <p className="rounded-xl bg-emerald-50 p-3 text-sm text-emerald-800 dark:bg-emerald-500/10 dark:text-emerald-300">
              Nada ha fallado.
            </p>
          )}
          {entries !== null && entries.length > 0 && (
            <ul className="space-y-2">
              {entries.map((entry) => (
                <ErrorRow key={entry.id} entry={entry} />
              ))}
            </ul>
          )}
        </div>
      )}
    </section>
  );
}
