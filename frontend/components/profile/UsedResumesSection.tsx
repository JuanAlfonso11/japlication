"use client";

import { useEffect, useMemo, useState } from "react";
import Link from "next/link";
import SectionCard from "@/components/profile/SectionCard";
import { ApiError, resumeApi } from "@/lib/api";
import type { ResumeVersion } from "@/lib/types";

function versionSubtitle(resume: ResumeVersion) {
  const date = new Date(resume.created_at).toLocaleDateString();
  return `${date} · ${resume.generated_by === "ai" ? "generado con IA" : "generado por reglas"}`;
}

function ChangeLog({ resume }: { resume: ResumeVersion }) {
  if (resume.change_log.length === 0) {
    return <p className="text-xs text-gray-400 dark:text-gray-400">Sin cambios registrados.</p>;
  }
  return (
    <ul className="list-inside list-disc space-y-0.5 text-xs text-gray-600 dark:text-gray-400">
      {resume.change_log.map((line, i) => (
        <li key={i}>{line}</li>
      ))}
    </ul>
  );
}

/** One job, every CV generated for it.
 *
 * Flat, this list printed a row per version: the same "Software Developer II
 * · Cision" nine times over, which reads as a bug rather than as history.
 * Grouped, the row is the job and the versions live inside it. */
function JobGroup({ versions }: { versions: ResumeVersion[] }) {
  const [expanded, setExpanded] = useState(false);
  const newest = versions[0];
  const jobLabel = newest.job ? `${newest.job.title} · ${newest.job.company}` : newest.title;

  return (
    <div className="rounded-xl border border-gray-200 p-4 dark:border-gray-700">
      <button
        type="button"
        onClick={() => setExpanded((v) => !v)}
        aria-expanded={expanded}
        className="flex w-full items-start justify-between gap-3 text-left"
      >
        <div className="min-w-0">
          <p className="line-clamp-2 font-medium text-gray-900 dark:text-gray-100">{jobLabel}</p>
          <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
            {versions.length === 1
              ? versionSubtitle(newest)
              : `${versions.length} versiones · la última, ${versionSubtitle(newest)}`}
          </p>
        </div>
        <span className="shrink-0 text-gray-400 dark:text-gray-400">{expanded ? "−" : "+"}</span>
      </button>

      {expanded && (
        <div className="mt-3 space-y-3 border-t border-gray-100 pt-3 dark:border-gray-800">
          {versions.map((resume) => (
            <div key={resume.id}>
              {versions.length > 1 && (
                <p className="mb-1 text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                  {versionSubtitle(resume)}
                </p>
              )}
              <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                Cambios respecto al CV base
              </p>
              <div className="mt-1">
                <ChangeLog resume={resume} />
              </div>
            </div>
          ))}
          {newest.job_id && (
            <Link
              href={`/jobs/${newest.job_id}`}
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

  // Grouped by job (by title when a version isn't tied to one), newest
  // version first inside each group and the most recently worked-on job
  // first overall.
  const groups = useMemo(() => {
    const byJob = new Map<string, ResumeVersion[]>();
    for (const resume of resumes ?? []) {
      const key = resume.job_id ?? `title:${resume.title}`;
      byJob.set(key, [...(byJob.get(key) ?? []), resume]);
    }
    const sorted = [...byJob.values()].map((versions) =>
      [...versions].sort((a, b) => Date.parse(b.created_at) - Date.parse(a.created_at))
    );
    return sorted.sort((a, b) => Date.parse(b[0].created_at) - Date.parse(a[0].created_at));
  }, [resumes]);

  return (
    <SectionCard
      title="CVs usados"
      description="Tu CV base es el que subiste o editaste arriba. Cada vez que generas un CV a medida para una vacante queda guardado aquí: puedes revisar qué se le cambió y reutilizarlo desde una vacante con requisitos parecidos en vez de generar uno nuevo."
    >
      {error && <p className="text-xs text-rose-600 dark:text-rose-400">{error}</p>}
      {resumes === null && !error && <p className="text-xs text-gray-400 dark:text-gray-400">Cargando…</p>}
      {resumes && resumes.length === 0 && (
        <p className="text-xs text-gray-400 dark:text-gray-400">
          Todavía no has generado ningún CV a medida. Hazlo desde la descripción de una vacante con el
          botón &quot;Generar CV&quot;.
        </p>
      )}
      {groups.length > 0 && (
        <div className="space-y-2">
          {groups.map((versions) => (
            <JobGroup key={versions[0].id} versions={versions} />
          ))}
        </div>
      )}
    </SectionCard>
  );
}
