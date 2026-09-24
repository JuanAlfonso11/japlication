import Link from "next/link";
import ScoreBadge from "@/components/ScoreBadge";
import SkillTag from "@/components/SkillTag";
import { buttonClass } from "@/components/ui/Button";
import type { AddedJob } from "@/lib/jobActions";

/** What happened to a job the user just added, and where to find it.
 *
 * `compact` is the one-line version shown right under the "Agregar" button
 * in Buscar; the full card was rendered at the bottom of the results, seven
 * phone screens below the button, so all anyone saw was "Agregado ✓". */
export default function ImportedJobCard({ job, compact = false }: { job: AddedJob; compact?: boolean }) {
  const inPipeline = Boolean(job.savedToPipeline);
  const headline = inPipeline ? "Guardada en tu Pipeline" : "Agregada a tu cola de Inicio";
  const note = inPipeline
    ? "Sube tu CV para ver qué tanto encaja y para que te preparemos el CV y la carta."
    : job.match
    ? "Ya tiene su puntaje. La vas a ver en Inicio para guardarla o pasarla."
    : null;

  const actions = (
    <div className={`flex flex-wrap gap-2 ${compact ? "mt-2" : "mt-4"}`}>
      {inPipeline ? (
        <>
          <Link href="/profile" className={buttonClass({ size: "sm" })}>
            Subir mi CV
          </Link>
          <Link href="/applications" className={buttonClass({ variant: "secondary", size: "sm" })}>
            Ver en Pipeline
          </Link>
        </>
      ) : (
        <Link href="/" className={buttonClass({ size: "sm" })}>
          Revisar en Inicio →
        </Link>
      )}
      <Link href={`/jobs/${job.id}`} className={buttonClass({ variant: "secondary", size: "sm" })}>
        Ver detalles
      </Link>
    </div>
  );

  if (compact) {
    return (
      <div role="status" className="mt-3 rounded-xl bg-emerald-50 p-3 ring-1 ring-inset ring-emerald-200 animate-fade-in dark:bg-emerald-500/10 dark:ring-emerald-500/30">
        <p className="text-xs font-bold text-emerald-800 dark:text-emerald-300">✓ {headline}</p>
        {note && <p className="mt-0.5 text-xs text-emerald-700 dark:text-emerald-400">{note}</p>}
        {actions}
      </div>
    );
  }

  return (
    <div className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-gray-100 animate-fade-in dark:bg-gray-900 dark:ring-gray-800">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-emerald-600 dark:text-emerald-400">
            {headline}
          </p>
          <h2 className="mt-1 text-xl font-bold text-gray-900 dark:text-gray-100">{job.title}</h2>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            {job.company}
            {job.location ? ` · ${job.location}` : ""}
          </p>
          {note && <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{note}</p>}
        </div>
        {job.match && <ScoreBadge score={job.match.overall_score} />}
      </div>

      {job.skills_required?.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {job.skills_required.slice(0, 12).map((s) => (
            <SkillTag key={s.name} label={s.name} />
          ))}
        </div>
      )}

      {job.requirements?.length > 0 && (
        <div className="mt-4">
          <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
            Requisitos
          </p>
          <ul className="list-inside list-disc space-y-1 text-sm text-gray-700 dark:text-gray-300">
            {job.requirements.slice(0, 6).map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </div>
      )}

      {actions}
    </div>
  );
}
