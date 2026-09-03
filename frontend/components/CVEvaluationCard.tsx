import type { CVEvaluation, CVIssue, IssueSeverity } from "@/lib/types";

const CATEGORY_LABELS: Record<string, string> = {
  completeness: "Completeness",
  impact: "Impact",
  skills_breadth: "Skills breadth",
  ats_safety: "ATS safety",
};

const SEVERITY_STYLES: Record<IssueSeverity, { dot: string; text: string }> = {
  error: { dot: "bg-rose-500", text: "text-rose-700 dark:text-rose-400" },
  warning: { dot: "bg-amber-500", text: "text-amber-700 dark:text-amber-400" },
  info: { dot: "bg-gray-400", text: "text-gray-600 dark:text-gray-400" },
};

function scoreColor(pct: number) {
  return pct >= 75 ? "bg-emerald-500" : pct >= 50 ? "bg-amber-500" : "bg-rose-500";
}

function ringColor(pct: number) {
  return pct >= 75
    ? "bg-emerald-100 text-emerald-700 ring-emerald-600/20 dark:bg-emerald-900/30 dark:text-emerald-300 dark:ring-emerald-400/30"
    : pct >= 50
    ? "bg-amber-100 text-amber-700 ring-amber-600/20 dark:bg-amber-900/30 dark:text-amber-300 dark:ring-amber-400/30"
    : "bg-rose-100 text-rose-700 ring-rose-600/20 dark:bg-rose-900/30 dark:text-rose-300 dark:ring-rose-400/30";
}

function CategoryBar({ label, value }: { label: string; value: number }) {
  const pct = Math.max(0, Math.min(100, value));
  return (
    <div>
      <div className="mb-1 flex items-center justify-between text-xs text-gray-600 dark:text-gray-400">
        <span>{label}</span>
        <span className="font-medium text-gray-800 dark:text-gray-200">{Math.round(pct)}</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-gray-100 dark:bg-gray-800">
        <div className={`h-full rounded-full ${scoreColor(pct)}`} style={{ width: `${pct}%` }} />
      </div>
    </div>
  );
}

function IssueRow({ issue }: { issue: CVIssue }) {
  const style = SEVERITY_STYLES[issue.severity] ?? SEVERITY_STYLES.info;
  return (
    <li className="flex items-start gap-2 text-sm">
      <span className={`mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full ${style.dot}`} />
      <span className="text-gray-700 dark:text-gray-300">{issue.message}</span>
    </li>
  );
}

export default function CVEvaluationCard({
  evaluation,
  loading,
  error,
}: {
  evaluation: CVEvaluation | null;
  loading: boolean;
  error: string | null;
}) {
  return (
    <div className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-gray-100 dark:bg-gray-900 dark:ring-gray-800">
      <div className="mb-3 flex items-start justify-between gap-3">
        <div>
          <div className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
            CV health check
          </div>
          <p className="mt-0.5 text-xs text-gray-400 dark:text-gray-500">
            Independent of any job — this is about the CV itself.
          </p>
        </div>
        {evaluation && (
          <span
            className={`inline-flex items-center gap-1 rounded-full px-3 py-1.5 text-lg font-semibold ring-1 ring-inset ${ringColor(
              evaluation.overall_score
            )}`}
          >
            {Math.round(evaluation.overall_score)}
            <span className="text-xs font-normal opacity-70">/100</span>
          </span>
        )}
      </div>

      {loading && <p className="text-sm text-gray-400 dark:text-gray-500">Evaluating your CV…</p>}
      {error && <p className="text-sm text-rose-600 dark:text-rose-400">{error}</p>}
      {!loading && !error && !evaluation && (
        <p className="text-sm text-gray-400 dark:text-gray-500">Save your profile below to see your CV health check.</p>
      )}

      {evaluation && (
        <div className="space-y-4">
          <div className="flex items-center gap-2">
            <span
              className={`rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ring-inset ${ringColor(
                evaluation.overall_score
              )}`}
            >
              {evaluation.band}
            </span>
            {evaluation.summary_generated_by === "ai" && (
              <span className="text-[11px] font-medium uppercase tracking-wide text-gray-400 dark:text-gray-500">
                AI summary
              </span>
            )}
          </div>

          <p className="text-sm text-gray-700 dark:text-gray-300">{evaluation.summary}</p>

          <div className="grid grid-cols-2 gap-x-6 gap-y-3 sm:grid-cols-4">
            {Object.entries(evaluation.categories).map(([key, cat]) => (
              <CategoryBar key={key} label={CATEGORY_LABELS[key] ?? key} value={cat.score} />
            ))}
          </div>

          {evaluation.top_issues.length > 0 && (
            <div>
              <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
                What to fix first
              </p>
              <ul className="space-y-1.5">
                {evaluation.top_issues.map((issue, i) => (
                  <IssueRow key={i} issue={issue} />
                ))}
              </ul>
            </div>
          )}

          {evaluation.strengths.length > 0 && (
            <div>
              <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
                Working well
              </p>
              <ul className="space-y-1.5">
                {evaluation.strengths.map((s, i) => (
                  <li key={i} className="flex items-start gap-2 text-sm text-gray-700 dark:text-gray-300">
                    <span className="mt-1.5 h-1.5 w-1.5 shrink-0 rounded-full bg-emerald-500" />
                    {s}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </div>
      )}
    </div>
  );
}
