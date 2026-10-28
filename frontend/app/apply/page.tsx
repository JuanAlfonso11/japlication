"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import ApplyModeSettings from "@/components/ApplyModeSettings";
import ErrorNotice from "@/components/ErrorNotice";
import RouteGuard from "@/components/RouteGuard";
import PageHeader from "@/components/ui/PageHeader";
import { ListSkeleton } from "@/components/ui/Skeleton";
import { ApiError, applyAgentApi } from "@/lib/api";
import { DRAFT_STATUS_LABELS, DRAFT_STATUS_TONE, TONE_CLASSES, describeDraft, isMoving } from "@/lib/applyDraft";
import type { ApplicationDraftListItem } from "@/lib/types";

/** Orden de la bandeja: primero lo que necesita al usuario. */
const ORDER: Record<string, number> = {
  needs_user: 0,
  ready: 1,
  handoff: 2,
  scheduled: 3,
  failed: 4,
  preparing: 5,
  submitting: 6,
  submitted: 7,
  cancelled: 8,
};

function ApplyTray() {
  const [items, setItems] = useState<ApplicationDraftListItem[] | null>(null);
  const [showAll, setShowAll] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [showSettings, setShowSettings] = useState(false);

  const load = useCallback(async () => {
    setError(null);
    try {
      const drafts = await applyAgentApi.drafts(!showAll);
      drafts.sort((a, b) => (ORDER[a.status] ?? 9) - (ORDER[b.status] ?? 9));
      setItems(drafts);
      return drafts;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo cargar la bandeja.");
      return null;
    }
  }, [showAll]);

  // Mientras algo se prepara o se envía, la lista se refresca sola.
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    let cancelled = false;
    async function tick() {
      const drafts = await load();
      if (cancelled) return;
      if (drafts?.some((d) => isMoving(d.status))) timer = setTimeout(tick, 3000);
    }
    tick();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [load]);

  return (
    <div className="mx-auto max-w-2xl space-y-4 animate-fade-in">
      <PageHeader
        title="Aplicaciones"
        subtitle="Lo que preparó tu swipe a la derecha. Primero lo que espera por ti."
        action={
          <button
            type="button"
            onClick={() => setShowSettings((v) => !v)}
            aria-expanded={showSettings}
            className="min-h-[36px] rounded-lg px-3 text-xs font-semibold text-gray-600 ring-1 ring-inset ring-gray-200 hover:bg-gray-50 dark:text-gray-300 dark:ring-gray-700 dark:hover:bg-gray-800"
          >
            Modo de swipe
          </button>
        }
      />

      {showSettings && (
        <section className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-gray-100 dark:bg-gray-900 dark:ring-gray-800">
          <ApplyModeSettings />
        </section>
      )}

      <div className="flex items-center gap-2 text-xs">
        <button
          type="button"
          onClick={() => setShowAll(false)}
          aria-pressed={!showAll}
          className={`min-h-[32px] rounded-full px-3 font-semibold ${
            !showAll ? "bg-brand-600 text-white dark:bg-brand-200 dark:text-gray-950" : "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300"
          }`}
        >
          En curso
        </button>
        <button
          type="button"
          onClick={() => setShowAll(true)}
          aria-pressed={showAll}
          className={`min-h-[32px] rounded-full px-3 font-semibold ${
            showAll ? "bg-brand-600 text-white dark:bg-brand-200 dark:text-gray-950" : "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300"
          }`}
        >
          Todas
        </button>
      </div>

      {error && <ErrorNotice message={error} onRetry={load} />}
      {!items && !error && <ListSkeleton rows={3} />}

      {items && items.length === 0 && (
        <div className="rounded-2xl bg-white/60 p-8 text-center ring-1 ring-inset ring-gray-200 dark:bg-gray-900/40 dark:ring-gray-800">
          <p className="font-display text-lg font-extrabold text-gray-900 dark:text-gray-100">Nada pendiente</p>
          <p className="mx-auto mt-1 max-w-[36ch] text-sm text-gray-500 dark:text-gray-400">
            Cuando deslices a la derecha, la aplicación aparece aquí mientras se prepara y hasta que sale.
          </p>
          <Link href="/" className="mt-3 inline-block text-sm font-bold text-brand-600 hover:underline dark:text-brand-300">
            Ir a Inicio
          </Link>
        </div>
      )}

      {items && items.length > 0 && (
        <ul className="space-y-2">
          {items.map((d) => (
            <li key={d.id}>
              <Link
                href={`/apply/${d.application_id}`}
                className="block rounded-2xl bg-white p-3.5 shadow-soft ring-1 ring-gray-100 transition-colors hover:bg-gray-50 dark:bg-gray-900 dark:ring-gray-800 dark:hover:bg-gray-800/70"
              >
                <div className="flex items-start justify-between gap-3">
                  <div className="min-w-0">
                    <p className="truncate text-sm font-semibold text-gray-900 dark:text-gray-100">
                      {d.job?.title ?? "Vacante"}
                    </p>
                    <p className="truncate text-xs text-gray-500 dark:text-gray-400">
                      {d.job?.company}
                      {d.channel === "email" ? " · por correo" : d.channel === "external" ? " · en su página" : ""}
                    </p>
                  </div>
                  <span
                    className={`shrink-0 rounded-full px-2 py-0.5 text-[11px] font-bold ring-1 ring-inset ${
                      TONE_CLASSES[DRAFT_STATUS_TONE[d.status]]
                    }`}
                  >
                    {DRAFT_STATUS_LABELS[d.status]}
                  </span>
                </div>
                <p className="mt-1.5 text-xs leading-relaxed text-gray-600 dark:text-gray-300">{describeDraft(d)}</p>
              </Link>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export default function ApplyTrayPage() {
  return (
    <RouteGuard>
      <ApplyTray />
    </RouteGuard>
  );
}
