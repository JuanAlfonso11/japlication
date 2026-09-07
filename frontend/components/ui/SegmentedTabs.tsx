"use client";

/** A segmented control for splitting one dense screen into sections.
 *
 * Used on Perfil, which had grown to thirteen stacked blocks — the CV form,
 * the answer bank, three analysis cards and the system panels all at once.
 * Sub-tabs rather than extra bottom-nav entries on purpose: the five-item
 * tab bar is already at a sensible density on a phone, and more importantly
 * the profile is a single form with a single save, so splitting it across
 * routes would mean either duplicating the save flow or sharing form state
 * between pages. Conditional rendering inside one form keeps both intact.
 */
export default function SegmentedTabs<T extends string>({
  tabs,
  value,
  onChange,
  className = "",
}: {
  tabs: { id: T; label: string; badge?: number }[];
  value: T;
  onChange: (id: T) => void;
  className?: string;
}) {
  return (
    <div
      role="tablist"
      aria-orientation="horizontal"
      className={`flex gap-1 rounded-xl bg-gray-100 p-1 dark:bg-gray-800 ${className}`}
    >
      {tabs.map((tab) => {
        const active = tab.id === value;
        return (
          <button
            key={tab.id}
            type="button"
            role="tab"
            aria-selected={active}
            onClick={() => onChange(tab.id)}
            className={`flex min-h-[38px] flex-1 items-center justify-center gap-1.5 rounded-lg px-2 text-[13px] font-semibold transition-all ${
              active
                ? "bg-white text-gray-900 shadow-soft dark:bg-gray-700 dark:text-gray-50"
                : "text-gray-500 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
            }`}
          >
            <span className="truncate">{tab.label}</span>
            {tab.badge !== undefined && tab.badge > 0 && (
              <span
                className={`tabular shrink-0 rounded-full px-1.5 text-[10px] font-bold ${
                  active
                    ? "bg-brand-100 text-brand-700 dark:bg-brand-500/25 dark:text-brand-200"
                    : "bg-gray-200 text-gray-500 dark:bg-gray-700 dark:text-gray-400"
                }`}
              >
                {tab.badge}
              </span>
            )}
          </button>
        );
      })}
    </div>
  );
}
