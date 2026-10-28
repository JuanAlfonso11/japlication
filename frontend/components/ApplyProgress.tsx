"use client";

import Link from "next/link";
import { useCallback, useEffect, useRef, useState } from "react";
import Button, { buttonClass } from "@/components/ui/Button";
import { ApiError, applyAgentApi } from "@/lib/api";
import { DRAFT_STATUS_LABELS, DRAFT_STATUS_TONE, TONE_CLASSES, describeDraft, isMoving } from "@/lib/applyDraft";
import type { ApplicationDraft, Job } from "@/lib/types";

const POLL_MS = 2000;
/** Lo que tarda de sobra en preparar una (CV con IA + formulario). Pasado
 * esto se deja de preguntar; la bandeja la sigue mostrando. */
const POLL_LIMIT_MS = 3 * 60 * 1000;

/** El aviso de Inicio justo después de un swipe a la derecha: sigue la
 * aplicación mientras se prepara y ofrece lo siguiente que hay que hacer
 * (responder, enviar, deshacer, o abrir la página de la empresa). */
export default function ApplyProgress({
  applicationId,
  job,
  onClose,
}: {
  applicationId: string;
  job: Job;
  onClose: () => void;
}) {
  const [draft, setDraft] = useState<ApplicationDraft | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const started = useRef(Date.now());

  const load = useCallback(async () => {
    try {
      const d = await applyAgentApi.get(applicationId);
      setDraft(d);
      return d;
    } catch (err) {
      // 404 = el swipe acaba de responder y la preparación aún no empezó.
      if (!(err instanceof ApiError && err.status === 404)) {
        setError(err instanceof ApiError ? err.message : "No se pudo consultar la aplicación.");
      }
      return null;
    }
  }, [applicationId]);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    let cancelled = false;
    started.current = Date.now();
    async function tick() {
      const d = await load();
      if (cancelled) return;
      const keepGoing = !d || isMoving(d.status);
      if (keepGoing && Date.now() - started.current < POLL_LIMIT_MS) {
        timer = setTimeout(tick, POLL_MS);
      }
    }
    tick();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [load]);

  async function undo() {
    setBusy(true);
    setError(null);
    try {
      setDraft(await applyAgentApi.cancel(applicationId));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo deshacer.");
    } finally {
      setBusy(false);
    }
  }

  const status = draft?.status ?? "preparing";
  const tone = TONE_CLASSES[DRAFT_STATUS_TONE[status]];
  const linea = draft
    ? describeDraft({
        status: draft.status,
        pending_count: draft.content.pending_required?.length ?? 0,
        handoff_reason: draft.content.handoff_reason ?? null,
        error: draft.error,
        scheduled_for: draft.scheduled_for,
        channel: draft.channel,
      })
    : describeDraft({
        status: "preparing",
        pending_count: 0,
        handoff_reason: null,
        error: null,
        scheduled_for: null,
        channel: "external",
      });
  const pagina = draft?.form_url || draft?.content.url || job.source_url || null;

  return (
    <div className="w-full max-w-md animate-slide-up rounded-2xl bg-white p-3.5 shadow-soft ring-1 ring-gray-100 dark:bg-gray-900 dark:ring-gray-800">
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <span className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-bold ring-1 ring-inset ${tone}`}>
            {isMoving(status) && (
              <span aria-hidden="true" className="h-1.5 w-1.5 animate-pulse rounded-full bg-current" />
            )}
            {DRAFT_STATUS_LABELS[status]}
          </span>
          <p className="mt-1.5 truncate text-[13px] font-semibold text-gray-900 dark:text-gray-100">
            {job.title} · {job.company}
          </p>
          <p className="mt-0.5 text-xs leading-relaxed text-gray-500 dark:text-gray-400" aria-live="polite">
            {linea}
          </p>
        </div>
        <button
          type="button"
          onClick={onClose}
          aria-label="Cerrar"
          className="-mr-1 -mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-700 dark:hover:bg-gray-800"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round"><path d="M18 6 6 18M6 6l12 12" /></svg>
        </button>
      </div>

      {error && <p className="mt-2 text-xs text-rose-600 dark:text-rose-400">{error}</p>}

      {draft && !isMoving(status) && status !== "cancelled" && (
        <div className="mt-2.5 flex flex-wrap gap-2">
          {status === "scheduled" && (
            <Button size="sm" variant="secondary" onClick={undo} loading={busy}>
              Deshacer
            </Button>
          )}
          {status === "handoff" && pagina && (
            <a href={pagina} target="_blank" rel="noreferrer" className={buttonClass({ size: "sm" })}>
              Abrir la página ↗
            </a>
          )}
          {status !== "submitted" && (
            <Link
              href={`/apply/${applicationId}`}
              className={buttonClass({ size: "sm", variant: status === "handoff" || status === "scheduled" ? "secondary" : "primary" })}
            >
              {status === "needs_user" ? "Responder" : status === "ready" ? "Revisar y enviar" : "Ver detalles"}
            </Link>
          )}
        </div>
      )}
    </div>
  );
}
