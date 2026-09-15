"use client";

import { useState } from "react";
import { resumeApi } from "@/lib/api";
import type { AtsReport } from "@/lib/types";

/**
 * Comprueba, antes de que lo mandes, que un ATS puede leer el PDF.
 *
 * El backend promete "ATS-safe" en nueve sitios y hasta ahora nadie lo
 * comprobaba: se renderizaba el PDF y no se volvía a abrir. El problema es que
 * este fallo no se ve — abres el PDF, se ve perfecto, y el formulario de
 * Greenhouse o Workday al otro lado lee la capa de texto, no la página. Si
 * ahí salen las palabras pegadas o falta tu correo, la candidatura no prospera
 * y nunca sabes por qué.
 *
 * Bajo demanda y no automático: renderizar el PDF otra vez cuesta, y el
 * momento en que esto importa es justo antes de enviarlo.
 */
export function AtsCheckPanel({ resumeVersionId }: { resumeVersionId: string }) {
  const [report, setReport] = useState<AtsReport | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function run() {
    setLoading(true);
    setError(null);
    try {
      setReport(await resumeApi.atsCheck(resumeVersionId));
    } catch {
      setError("No se pudo revisar el PDF.");
    } finally {
      setLoading(false);
    }
  }

  const errores = report?.findings.filter((f) => f.level === "error") ?? [];
  const avisos = report?.findings.filter((f) => f.level === "warning") ?? [];

  return (
    <div className="mt-2">
      <button
        type="button"
        onClick={run}
        disabled={loading}
        className="rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-semibold text-gray-600 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800"
        title="Lee el PDF de vuelta y comprueba que un sistema de selección automática lo entiende"
      >
        {loading ? "Revisando…" : report ? "Revisar otra vez" : "¿Lo lee un ATS?"}
      </button>

      {error && <p className="mt-1 text-xs text-rose-600 dark:text-rose-400">{error}</p>}

      {report && (
        <div
          className={`mt-2 rounded-lg p-3 text-xs ring-1 ring-inset ${
            report.readable
              ? "bg-emerald-50 text-emerald-800 ring-emerald-600/20 dark:bg-emerald-900/20 dark:text-emerald-300 dark:ring-emerald-400/30"
              : "bg-rose-50 text-rose-800 ring-rose-600/20 dark:bg-rose-900/20 dark:text-rose-300 dark:ring-rose-400/30"
          }`}
        >
          <p className="font-semibold">
            {report.readable
              ? "Un ATS puede leer este PDF."
              : "Un ATS NO leería bien este PDF."}
          </p>

          {errores.map((f) => (
            <p key={f.code} className="mt-1.5">
              ⚠ {f.message}
            </p>
          ))}
          {avisos.map((f) => (
            <p key={f.code} className="mt-1.5 opacity-90">
              {f.message}
            </p>
          ))}

          {/* El dato concreto, no solo el veredicto: si algún día el chequeo se
              equivoca, esto es lo que deja verlo. */}
          <p className="mt-2 opacity-70">
            {report.pages} {report.pages === 1 ? "página" : "páginas"} ·{" "}
            {report.extracted_chars.toLocaleString("es")} caracteres legibles
            {report.keywords_found.length > 0 &&
              ` · ${report.keywords_found.length} de ${
                report.keywords_found.length + report.keywords_missing.length
              } habilidades detectadas`}
          </p>
        </div>
      )}
    </div>
  );
}

export default AtsCheckPanel;
