export default function ScoreBadge({
  score,
  size = "md",
}: {
  score: number;
  size?: "sm" | "md" | "lg";
}) {
  const color =
    score >= 75
      ? "bg-emerald-100 text-emerald-700 ring-emerald-600/20 dark:bg-emerald-900/30 dark:text-emerald-300 dark:ring-emerald-400/30"
      : score >= 50
      ? "bg-amber-100 text-amber-700 ring-amber-600/20 dark:bg-amber-900/30 dark:text-amber-300 dark:ring-amber-400/30"
      : "bg-rose-100 text-rose-700 ring-rose-600/20 dark:bg-rose-900/30 dark:text-rose-300 dark:ring-rose-400/30";

  const sizeClasses =
    size === "lg"
      ? "text-2xl px-4 py-2"
      : size === "sm"
      ? "text-xs px-2 py-0.5"
      : "text-sm px-2.5 py-1";

  return (
    <span
      className={`inline-flex items-center gap-1 rounded-full font-semibold ring-1 ring-inset ${color} ${sizeClasses}`}
    >
      {Math.round(score)}
      <span className="opacity-70">%</span>
    </span>
  );
}
