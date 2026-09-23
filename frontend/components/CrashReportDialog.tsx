"use client";

import { useEffect, useState, useSyncExternalStore } from "react";
import Button from "@/components/ui/Button";
import { inputClass } from "@/components/ui/Field";
import {
  dismissPendingReport,
  getPendingReport,
  sendPendingReport,
  subscribeToPendingReport,
} from "@/lib/errorReporting";

/** "Algo falló — ¿reportar el fallo?" Shown for any captured crash
 * (lib/errorReporting.ts). Nothing leaves the phone unless the user taps
 * Reportar. Mounted outside the ErrorBoundary so it survives a page crash. */
export default function CrashReportDialog() {
  const report = useSyncExternalStore(subscribeToPendingReport, getPendingReport, () => null);
  const [note, setNote] = useState("");
  const [sending, setSending] = useState(false);
  const [thanks, setThanks] = useState(false);

  useEffect(() => {
    if (!thanks) return;
    const t = setTimeout(() => setThanks(false), 3000);
    return () => clearTimeout(t);
  }, [thanks]);

  if (thanks) {
    return (
      <div
        role="status"
        className="fixed inset-x-4 bottom-24 z-[60] mx-auto max-w-sm rounded-2xl bg-gray-900 px-4 py-3 text-center text-sm font-semibold text-white shadow-card dark:bg-gray-100 dark:text-gray-900"
      >
        Gracias, recibimos el reporte.
      </div>
    );
  }

  if (!report) return null;

  async function handleSend() {
    setSending(true);
    await sendPendingReport(note);
    setSending(false);
    setNote("");
    setThanks(true);
  }

  function handleDismiss() {
    setNote("");
    dismissPendingReport();
  }

  return (
    <div className="fixed inset-0 z-[60] flex items-end justify-center bg-black/40 p-4 sm:items-center">
      <div
        role="dialog"
        aria-modal="true"
        aria-labelledby="crash-report-title"
        className="w-full max-w-sm rounded-3xl bg-white p-5 shadow-card ring-1 ring-gray-100 dark:bg-gray-900 dark:ring-gray-800"
      >
        <h2 id="crash-report-title" className="font-display text-lg font-extrabold tracking-display-tight text-gray-900 dark:text-gray-100">
          Algo falló
        </h2>
        <p className="mt-1 text-sm leading-relaxed text-gray-500 dark:text-gray-400">
          ¿Nos envías un reporte del fallo? Incluye el detalle técnico del error (no tu CV ni tus
          datos) y nos ayuda a arreglarlo.
        </p>
        <label htmlFor="crash-report-note" className="mt-4 mb-1.5 block text-xs font-semibold text-gray-600 dark:text-gray-400">
          ¿Qué estabas haciendo? (opcional)
        </label>
        <textarea
          id="crash-report-note"
          rows={3}
          maxLength={500}
          value={note}
          onChange={(e) => setNote(e.target.value)}
          className={`${inputClass} resize-none`}
          placeholder="Ej.: tocaba Guardar en una vacante"
        />
        <div className="mt-4 flex gap-2">
          <Button variant="secondary" fullWidth onClick={handleDismiss} disabled={sending}>
            Ahora no
          </Button>
          <Button fullWidth onClick={handleSend} loading={sending}>
            Reportar el fallo
          </Button>
        </div>
      </div>
    </div>
  );
}
