/** The match score, the one number the whole app is built around.
 *
 * At `lg` (the swipe card, job detail) it renders as a progress ring rather
 * than a flat pill: the filled arc communicates "72 out of 100" pre-verbally,
 * before the digits are even read, and it's the app's most recognizable
 * single element. `sm`/`md` stay pills — inside dense lists a ring would be
 * noise, and the number alone is enough once the ring has taught the scale.
 *
 * Color is semantic (how good is this match), not decorative, so it stays on
 * the emerald → amber → rose ramp instead of the brand hue. */

type Tier = {
  ring: string;
  track: string;
  pill: string;
  label: string;
};

function tierFor(score: number): Tier {
  if (score >= 75) {
    return {
      ring: "text-emerald-500",
      track: "text-emerald-500/15",
      pill: "bg-emerald-50 text-emerald-700 ring-emerald-600/20 dark:bg-emerald-500/10 dark:text-emerald-300 dark:ring-emerald-400/30",
      label: "Alta coincidencia",
    };
  }
  if (score >= 50) {
    return {
      ring: "text-accent-500",
      track: "text-accent-500/15",
      pill: "bg-accent-50 text-accent-700 ring-accent-600/20 dark:bg-accent-500/10 dark:text-accent-300 dark:ring-accent-400/30",
      label: "Coincidencia media",
    };
  }
  return {
    ring: "text-rose-500",
    track: "text-rose-500/15",
    pill: "bg-rose-50 text-rose-700 ring-rose-600/20 dark:bg-rose-500/10 dark:text-rose-300 dark:ring-rose-400/30",
    label: "Coincidencia baja",
  };
}

const RADIUS = 26;
const CIRCUMFERENCE = 2 * Math.PI * RADIUS;

export default function ScoreBadge({
  score,
  size = "md",
}: {
  score: number;
  size?: "sm" | "md" | "lg";
}) {
  const rounded = Math.round(score);
  const tier = tierFor(score);

  if (size === "lg") {
    const clamped = Math.max(0, Math.min(100, score));
    return (
      <div
        className="relative flex h-16 w-16 shrink-0 items-center justify-center"
        role="img"
        aria-label={`${rounded}% — ${tier.label}`}
      >
        <svg viewBox="0 0 64 64" className="h-full w-full -rotate-90">
          <circle
            cx="32"
            cy="32"
            r={RADIUS}
            fill="none"
            strokeWidth="6"
            stroke="currentColor"
            className={tier.track}
          />
          <circle
            cx="32"
            cy="32"
            r={RADIUS}
            fill="none"
            strokeWidth="6"
            strokeLinecap="round"
            stroke="currentColor"
            className={tier.ring}
            strokeDasharray={CIRCUMFERENCE}
            strokeDashoffset={CIRCUMFERENCE * (1 - clamped / 100)}
          />
        </svg>
        <span className="absolute inset-0 flex flex-col items-center justify-center">
          <span className="tabular font-display text-lg font-extrabold leading-none text-gray-900 dark:text-gray-100">
            {rounded}
          </span>
          <span className="text-[9px] font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">
            match
          </span>
        </span>
      </div>
    );
  }

  const sizeClasses = size === "sm" ? "text-xs px-2 py-0.5" : "text-sm px-2.5 py-1";

  return (
    <span
      title={tier.label}
      className={`tabular inline-flex items-center gap-0.5 rounded-full font-semibold ring-1 ring-inset ${tier.pill} ${sizeClasses}`}
    >
      {rounded}
      <span className="opacity-60">%</span>
    </span>
  );
}
