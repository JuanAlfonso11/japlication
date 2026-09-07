import type { ReactNode } from "react";

/** The title block every non-Home screen opens with.
 *
 * Each page used to hand-roll this (`text-2xl font-bold` here, `text-xl`
 * there, some with a subtitle, some without), so moving between tabs meant
 * the heading visibly changed size and weight. One component, one scale. */
export default function PageHeader({
  title,
  subtitle,
  action,
}: {
  title: string;
  subtitle?: string;
  /** Optional trailing control (a button, a link) pinned to the right on
   * wide screens and dropped below the text on narrow ones. */
  action?: ReactNode;
}) {
  return (
    <div className="flex flex-wrap items-start justify-between gap-3">
      <div className="min-w-0">
        <h1 className="font-display text-[26px] font-extrabold leading-tight tracking-display-tight text-gray-900 dark:text-gray-50">
          {title}
        </h1>
        {subtitle && (
          <p className="mt-1 max-w-[52ch] text-sm leading-relaxed text-gray-500 dark:text-gray-400">
            {subtitle}
          </p>
        )}
      </div>
      {action && <div className="shrink-0">{action}</div>}
    </div>
  );
}
