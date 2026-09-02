import type { MatchResult } from "@/lib/types";

function ScoreBar({ label, value }: { label: string; value: number }) {
  const pct = Math.max(0, Math.min(100, value));
  const barColor =
    pct >= 75 ? "bg-emerald-500" : pct >= 50 ? "bg-amber-500" : "bg-rose-500";
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-xs text-gray-600">
        <span>{label}</span>
        <span className="font-medium text-gray-800">{Math.round(pct)}%</span>
      </div>
      <div className="h-2 w-full overflow-hidden rounded-full bg-gray-100">
        <div className={`h-full rounded-full ${barColor}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

export default function MatchBreakdown({ match }: { match: MatchResult }) {
  return (
    <div className="space-y-3">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <ScoreBar label="Technical" value={match.technical_score} />
        <ScoreBar label="Experience" value={match.experience_score} />
        <ScoreBar label="Semantic fit" value={match.semantic_score} />
      </div>

      {match.matched_skills.length > 0 && (
        <div>
          <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-gray-500">
            Matched skills
          </p>
          <div className="flex flex-wrap gap-1.5">
            {match.matched_skills.map((s) => (
              <span
                key={s}
                className="rounded-full bg-emerald-50 px-2.5 py-1 text-xs font-medium text-emerald-700 ring-1 ring-inset ring-emerald-600/20"
              >
                {s}
              </span>
            ))}
          </div>
        </div>
      )}

      {match.missing_skills.length > 0 && (
        <div>
          <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-gray-500">
            Missing skills
          </p>
          <div className="flex flex-wrap gap-1.5">
            {match.missing_skills.map((s) => (
              <span
                key={s}
                className="rounded-full bg-rose-50 px-2.5 py-1 text-xs font-medium text-rose-700 ring-1 ring-inset ring-rose-600/20"
              >
                {s}
              </span>
            ))}
          </div>
        </div>
      )}

      {match.concerns.length > 0 && (
        <div>
          <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-gray-500">
            Concerns
          </p>
          <ul className="list-inside list-disc space-y-0.5 text-sm text-gray-600">
            {match.concerns.map((c, i) => (
              <li key={i}>{c}</li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
