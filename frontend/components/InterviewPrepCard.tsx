"use client";

import { useState } from "react";
import ErrorNotice from "@/components/ErrorNotice";
import Button from "@/components/ui/Button";
import { ApiError, jobsApi } from "@/lib/api";
import type { InterviewPrepResponse } from "@/lib/types";

/** The questions this posting is likely to produce, and what in your own
 * history answers them.
 *
 * The app used to stop at "application sent" — it found the job, scored it,
 * tailored the CV and drafted the letter, then left you at the hard part.
 *
 * Generated on demand rather than with the page: it's the last thing you
 * need, often days after applying, and for most postings it's never opened.
 */

const CATEGORY_STYLES: Record<string, { label: string; className: string }> = {
  tecnica: {
    label: "Técnica",
    className: "bg-brand-50 text-brand-700 dark:bg-brand-500/15 dark:text-brand-300",
  },
  brecha: {
    label: "Brecha",
    className: "bg-rose-50 text-rose-700 dark:bg-rose-500/15 dark:text-rose-300",
  },
  requisito: {
    label: "Requisito",
    className: "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300",
  },
  empresa: {
    label: "Empresa",
    className: "bg-accent-50 text-accent-700 dark:bg-accent-500/15 dark:text-accent-300",
  },
};

export default function InterviewPrepCard({ jobId }: { jobId: string }) {
  const [prep, setPrep] = useState<InterviewPrepResponse | null>(null);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function generate() {
    setLoading(true);
    setError(null);
    try {
      setPrep(await jobsApi.interviewPrep(jobId));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo preparar la entrevista.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <div className="rounded-2xl bg-white p-5 shadow-soft ring-1 ring-gray-100 dark:bg-gray-900 dark:ring-gray-800">
      <div className="mb-3 flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0">
          <h2 className="font-display font-bold text-gray-900 dark:text-gray-100">
            Preparación de entrevista
          </h2>
          <p className="mt-0.5 text-xs leading-relaxed text-gray-500 dark:text-gray-400">
            Las preguntas que esta vacante va a producir, y qué de tu experiencia las responde.
          </p>
        </div>
        <Button size="sm" onClick={generate} loading={loading} className="shrink-0">
          {loading ? "Preparando…" : prep ? "Regenerar" : "Preparar"}
        </Button>
      </div>

      {error && <ErrorNotice message={error} />}

      {prep && (
        <div className="space-y-3">
          {prep.questions.map((q, i) => {
            const style = CATEGORY_STYLES[q.category] ?? CATEGORY_STYLES.requisito;
            return (
              <div key={i} className="rounded-xl bg-gray-50 p-3.5 dark:bg-gray-800/60">
                <div className="mb-1.5 flex items-start justify-between gap-2">
                  <p className="min-w-0 text-sm font-semibold leading-snug text-gray-900 dark:text-gray-100">
                    {q.question}
                  </p>
                  <span
                    className={`shrink-0 rounded-full px-2 py-0.5 text-[10px] font-bold uppercase tracking-wide ${style.className}`}
                  >
                    {style.label}
                  </span>
                </div>

                {q.why && (
                  // Upright, not italic: an italic accent line is decoration
                  // borrowed from template layouts, and at 11px it is the
                  // hardest text on the card to read.
                  <p className="mb-2 text-[11px] text-gray-500 dark:text-gray-400">{q.why}</p>
                )}

                {q.talking_points.length > 0 && (
                  <ul className="space-y-1.5">
                    {q.talking_points.map((point, j) => (
                      <li
                        key={j}
                        className="flex gap-2 text-[13px] leading-relaxed text-gray-700 dark:text-gray-300"
                      >
                        <span className="mt-[7px] h-1 w-1 shrink-0 rounded-full bg-brand-400" />
                        <span>{point}</span>
                      </li>
                    ))}
                  </ul>
                )}
              </div>
            );
          })}

          <p className="text-[11px] leading-relaxed text-gray-400 dark:text-gray-400">
            {prep.generated_by === "ai"
              ? "Generado con IA a partir de tu perfil y esta vacante. Nunca inventa experiencia que no declaraste."
              : "Generado a partir de tu perfil y esta vacante, sin IA. Los puntos salen de tus propias viñetas."}
          </p>
        </div>
      )}
    </div>
  );
}
