import type { MatchResult } from "@/lib/types";

/** Section heading shared by every block below — one weight, one size, one
 * tracking value, so the card reads as a single document rather than three
 * separately-styled panels. */
function SectionLabel({ children }: { children: React.ReactNode }) {
  return (
    <p className="mb-2 text-[10px] font-bold uppercase tracking-[0.08em] text-gray-400 dark:text-gray-500">
      {children}
    </p>
  );
}

function ScoreBar({ label, value }: { label: string; value: number }) {
  const pct = Math.max(0, Math.min(100, value));
  const barColor = pct >= 75 ? "bg-emerald-500" : pct >= 50 ? "bg-accent-400" : "bg-rose-500";
  return (
    <div>
      <div className="mb-1.5 flex items-center justify-between gap-2 text-[11px]">
        <span className="font-medium text-gray-500 dark:text-gray-400">{label}</span>
        <span className="tabular font-bold text-gray-800 dark:text-gray-200">{Math.round(pct)}%</span>
      </div>
      <div className="h-1.5 w-full overflow-hidden rounded-full bg-gray-100 dark:bg-gray-800">
        {/* The width transition makes the bars sweep out when a card lands
            instead of appearing pre-filled — the one place in the card where
            a little motion actually conveys "this was just computed for you". */}
        <div
          className={`h-full rounded-full transition-[width] duration-500 ease-out ${barColor}`}
          style={{ width: `${pct}%` }}
        />
      </div>
    </div>
  );
}

function SkillPills({ skills, tone }: { skills: string[]; tone: "matched" | "missing" }) {
  const style =
    tone === "matched"
      ? "bg-emerald-50 text-emerald-700 ring-emerald-600/20 dark:bg-emerald-500/10 dark:text-emerald-300 dark:ring-emerald-400/25"
      : "bg-rose-50 text-rose-700 ring-rose-600/20 dark:bg-rose-500/10 dark:text-rose-300 dark:ring-rose-400/25";
  return (
    <div className="flex flex-wrap gap-1.5">
      {skills.map((s) => (
        <span
          key={s}
          className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ring-1 ring-inset ${style}`}
        >
          {s}
        </span>
      ))}
    </div>
  );
}

export default function MatchBreakdown({ match }: { match: MatchResult }) {
  return (
    <div className="space-y-4">
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-3">
        <ScoreBar label="Técnico" value={match.technical_score} />
        <ScoreBar label="Experiencia" value={match.experience_score} />
        <ScoreBar label="Afinidad" value={match.semantic_score} />
      </div>

      {match.matched_skills.length > 0 && (
        <div>
          <SectionLabel>Habilidades que coinciden</SectionLabel>
          <SkillPills skills={match.matched_skills} tone="matched" />
        </div>
      )}

      {match.missing_skills.length > 0 && (
        <div>
          <SectionLabel>Habilidades que faltan</SectionLabel>
          <SkillPills skills={match.missing_skills} tone="missing" />
        </div>
      )}

      {match.concerns.length > 0 && (
        <div>
          <SectionLabel>Puntos a considerar</SectionLabel>
          <ul className="space-y-1.5">
            {match.concerns.map((c, i) => (
              <li key={i} className="flex gap-2 text-[13px] leading-snug text-gray-600 dark:text-gray-400">
                <span className="mt-[6px] h-1 w-1 shrink-0 rounded-full bg-gray-300 dark:bg-gray-600" />
                <span>{c}</span>
              </li>
            ))}
          </ul>
        </div>
      )}
    </div>
  );
}
