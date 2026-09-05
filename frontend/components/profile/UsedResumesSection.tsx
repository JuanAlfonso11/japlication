"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import SectionCard from "@/components/profile/SectionCard";
import { ApiError, resumeApi } from "@/lib/api";
import type { ResumeVersion } from "@/lib/types";

function ResumeVersionRow({ resume }: { resume: ResumeVersion }) {
  const [expanded, setExpanded] = useState(false);
  const jobLabel = resume.job ? `${resume.job.title} · ${resume.job.company}` : resume.title;

  return (
    <div className="rounded-xl border border-gray-200 p-4 dark:border-gray-700">
      <button type="button" onClick={() => setExpanded((v) => !v)} className="flex w-full items-start justify-between gap-3 text-left">
        <div className="min-w-0">
          <p className="truncate font-medium text-gray-900 dark:text-gray-100">{jobLabel}</p>
          <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
            {new Date(resume.created_at).toLocaleDateString()} ·{" "}
            {resume.generated_by === "ai" ? "generado con IA" : "generado por reglas"}
          </p>
        </div>
        <span className="shrink-0 text-gray-400 dark:text-gray-500">{expanded ? "−" : "+"}</span>
      </button>
      {expanded && (
        <div className="mt-3 space-y-3 border-t border-gray-100 pt-3 dark:border-gray-800">
          {resume.change_log.length > 0 ? (
            <div>
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                Cambios respecto al CV base
              </p>
              <ul className="mt-1 list-inside list-disc space-y-0.5 text-xs text-gray-600 dark:text-gray-400">
                {resume.change_log.map((line, i) => (
                  <li key={i}>{line}</li>
                ))}
              </ul>
            </div>
          ) : (
            <p className="text-xs text-gray-400 dark:text-gray-500">Sin cambios registrados.</p>
          )}
          {resume.job_id && (
            <Link
              href={`/jobs/${resume.job_id}`}
              className="inline-block text-xs font-medium text-brand-600 hover:underline dark:text-brand-400"
            >
              Ver vacante ↗
            </Link>
          )}
        </div>
      )}
    </div>
  );
}

export default function UsedResumesSection() {
  const [resumes, setResumes] = useState<ResumeVersion[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    resumeApi
      .list()
      .then(setResumes)
      .catch((err) => setError(err instanceof ApiError ? err.message : "No se pudieron cargar los CVs."));
  }, []);

  return (
    <SectionCard
      title="CVs usados"
      description="Tu CV base es el que subiste/editaste arriba. Cada vez que generas un CV a medida para una vacante, queda guardado aquí — puedes revisar qué se le cambió, y reutilizarlo directamente desde la descripción de una vacante con requisitos parecidos en vez de generar uno nuevo."
    >
      {error && <p className="text-xs text-rose-600 dark:text-rose-400">{error}</p>}
      {resumes === null && !error && <p className="text-xs text-gray-400 dark:text-gray-500">Cargando…</p>}
      {resumes && resumes.length === 0 && (
        <p className="text-xs text-gray-400 dark:text-gray-500">
          Todavía no has generado ningún CV a medida — hazlo desde la descripción de una vacante con el
          botón &quot;Generar CV&quot;.
        </p>
      )}
      {resumes && resumes.length > 0 && (
        <div className="space-y-2">
          {resumes.map((r) => (
            <ResumeVersionRow key={r.id} resume={r} />
          ))}
        </div>
      )}
    </SectionCard>
  );
}
