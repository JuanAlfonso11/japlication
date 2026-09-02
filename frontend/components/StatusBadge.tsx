import type { ApplicationStatus } from "@/lib/types";

const STATUS_STYLES: Record<string, string> = {
  queued: "bg-gray-100 text-gray-700 ring-gray-500/20",
  saved: "bg-brand-50 text-brand-700 ring-brand-600/20",
  passed: "bg-gray-100 text-gray-500 ring-gray-400/20",
  applied: "bg-indigo-50 text-indigo-700 ring-indigo-600/20",
  interviewing: "bg-amber-50 text-amber-700 ring-amber-600/20",
  offer: "bg-emerald-50 text-emerald-700 ring-emerald-600/20",
  rejected: "bg-rose-50 text-rose-700 ring-rose-600/20",
  withdrawn: "bg-gray-100 text-gray-500 ring-gray-400/20",
};

export const STATUS_LABELS: Record<string, string> = {
  queued: "Queued",
  saved: "Saved",
  passed: "Passed",
  applied: "Applied",
  interviewing: "Interviewing",
  offer: "Offer",
  rejected: "Rejected",
  withdrawn: "Withdrawn",
};

export default function StatusBadge({ status }: { status: ApplicationStatus | string }) {
  const style = STATUS_STYLES[status] ?? "bg-gray-100 text-gray-700 ring-gray-500/20";
  const label = STATUS_LABELS[status] ?? status;
  return (
    <span
      className={`inline-flex items-center rounded-full px-2.5 py-1 text-xs font-semibold ring-1 ring-inset ${style}`}
    >
      {label}
    </span>
  );
}
