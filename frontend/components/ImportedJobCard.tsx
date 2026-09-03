import Link from "next/link";
import ScoreBadge from "@/components/ScoreBadge";
import SkillTag from "@/components/SkillTag";
import type { Job } from "@/lib/types";

export default function ImportedJobCard({ job }: { job: Job }) {
  return (
    <div className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-gray-100 animate-fade-in">
      <div className="flex items-start justify-between gap-3">
        <div>
          <p className="text-xs font-semibold uppercase tracking-wide text-emerald-600">
            Added to your queue
          </p>
          <h2 className="mt-1 text-xl font-bold text-gray-900">{job.title}</h2>
          <p className="text-sm text-gray-600">
            {job.company}
            {job.location ? ` · ${job.location}` : ""}
          </p>
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
          <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-gray-500">
            Requirements
          </p>
          <ul className="list-inside list-disc space-y-1 text-sm text-gray-700">
            {job.requirements.slice(0, 6).map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="mt-4 flex flex-wrap gap-2">
        <Link
          href="/"
          className="inline-flex items-center gap-1 rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700"
        >
          Review in Home
          <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14M13 5l7 7-7 7" /></svg>
        </Link>
        <Link
          href={`/jobs/${job.id}`}
          className="inline-flex items-center gap-1 rounded-lg border border-gray-200 px-4 py-2 text-sm font-semibold text-gray-600 hover:bg-gray-50"
        >
          View details
        </Link>
      </div>
    </div>
  );
}
