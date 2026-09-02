export default function SkillTag({
  label,
  tone = "default",
}: {
  label: string;
  tone?: "default" | "positive" | "negative";
}) {
  const toneClasses =
    tone === "positive"
      ? "bg-emerald-50 text-emerald-700 ring-emerald-600/20"
      : tone === "negative"
      ? "bg-rose-50 text-rose-700 ring-rose-600/20"
      : "bg-brand-50 text-brand-700 ring-brand-600/20";

  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-medium ring-1 ring-inset ${toneClasses}`}
    >
      {label}
    </span>
  );
}
