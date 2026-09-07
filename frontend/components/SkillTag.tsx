export default function SkillTag({
  label,
  tone = "default",
}: {
  label: string;
  tone?: "default" | "positive" | "negative";
}) {
  const toneClasses =
    tone === "positive"
      ? "bg-emerald-50 text-emerald-700 ring-emerald-600/20 dark:bg-emerald-500/10 dark:text-emerald-300 dark:ring-emerald-400/25"
      : tone === "negative"
      ? "bg-rose-50 text-rose-700 ring-rose-600/20 dark:bg-rose-500/10 dark:text-rose-300 dark:ring-rose-400/25"
      : "bg-brand-50 text-brand-700 ring-brand-600/15 dark:bg-brand-500/10 dark:text-brand-300 dark:ring-brand-400/25";

  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-1 text-[11px] font-semibold ring-1 ring-inset ${toneClasses}`}
    >
      {label}
    </span>
  );
}
