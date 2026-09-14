"use client";

import { useEffect, useState } from "react";
import { jobsApi } from "@/lib/api";
import type { SkillGapsResponse } from "@/lib/types";

/** What to learn next, derived from every job you said yes to.
 *
 * The match engine already explains one posting's score. This is the
 * pattern across them — the question a job seeker actually has ("what do I
 * keep getting rejected for?") and the one thing here that none of the
 * auto-apply tools can answer, because none of them score you against a
 * profile in the first place.
 *
 * Deliberately shows a bar per skill rather than a number: the point isn't
 * "Kubernetes: 9", it's that Kubernetes is twice the problem Terraform is,
 * and length says that instantly. */
export default function SkillGapsCard() {
  const [data, setData] = useState<SkillGapsResponse | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    jobsApi
      .skillGaps()
      .then((res) => {
        if (!cancelled) setData(res);
      })
      .catch(() => {
        // A derived insight is not worth an error state on the profile page.
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  // Nothing to say yet (no scored jobs, or no repeated gap) — stay out of
  // the way instead of rendering an empty shell.
  if (loading || !data || data.gaps.length === 0) return null;

  const max = Math.max(...data.gaps.map((g) => g.percentage));

  return (
    <section className="rounded-2xl bg-white p-5 shadow-soft ring-1 ring-gray-100 dark:bg-gray-900 dark:ring-gray-800">
      <div className="mb-1 flex items-start justify-between gap-3">
        <h2 className="font-display font-bold text-gray-900 dark:text-gray-100">
          Qué te falta para subir el score
        </h2>
        <span className="tabular shrink-0 rounded-full bg-gray-100 px-2.5 py-1 text-[11px] font-bold text-gray-500 dark:bg-gray-800 dark:text-gray-400">
          {data.jobs_considered} vacantes
        </span>
      </div>

      <p className="mb-4 text-xs leading-relaxed text-gray-500 dark:text-gray-400">
        {data.based_on_all_matches
          ? "Calculado sobre todas las vacantes puntuadas. Guarda algunas más y esto se afinará a lo que de verdad te interesa."
          : data.summary ?? "Las habilidades que más se repiten en lo que guardaste y no están en tu perfil."}
      </p>

      <ul className="space-y-2.5">
        {data.gaps.map((gap) => (
          <li key={gap.skill}>
            <div className="mb-1 flex items-baseline justify-between gap-3">
              <span className="truncate text-sm font-semibold text-gray-800 dark:text-gray-200">
                {gap.skill}
              </span>
              <span className="tabular shrink-0 text-[11px] font-bold text-gray-400 dark:text-gray-400">
                {gap.percentage}%
              </span>
            </div>
            <div className="h-1.5 w-full overflow-hidden rounded-full bg-gray-100 dark:bg-gray-800">
              <div
                className="h-full rounded-full bg-brand-600 transition-[width] duration-500 ease-out dark:bg-brand-200"
                /* Scaled against the top gap, not against 100 — with a
                   worst gap of 40% every bar would otherwise be a stub and
                   the comparison, which is the whole point, disappears. */
                style={{ width: `${Math.round((gap.percentage / max) * 100)}%` }}
              />
            </div>
          </li>
        ))}
      </ul>

      <p className="mt-4 text-[11px] leading-relaxed text-gray-400 dark:text-gray-400">
        Si ya tienes alguna de estas, agrégala a tus habilidades arriba: el score sube solo.
      </p>
    </section>
  );
}
