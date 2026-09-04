import type { ReactNode, SelectHTMLAttributes } from "react";

/** Shared form-control styling — the single source of truth for how every
 * input/select/textarea looks across the app (Discover's filters,
 * Login/Register, Profile's sub-forms, Applications' status picker, ...).
 * Before this existed each page hand-copied its own Tailwind string, which
 * is why paddings/widths had drifted out of sync (py-2, py-2.5, py-1.5all
 * present at once) — see the design-consistency pass this file is part of. */

export function FormField({
  label,
  children,
  className = "",
}: {
  label: string;
  children: ReactNode;
  className?: string;
}) {
  return (
    <label className={`block ${className}`}>
      <span className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">{label}</span>
      {children}
    </label>
  );
}

export const inputClass =
  "w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm text-gray-900 outline-none transition-colors focus:border-brand-500 focus:ring-2 focus:ring-brand-100 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:focus:ring-brand-900/40";

export const textareaClass = `${inputClass} min-h-[80px] resize-y`;

/** Base class for a `<select>` trigger — `appearance-none` strips the
 * browser/OS-native arrow (which looks different per platform) so the
 * `Select` component below can draw one consistent chevron over it
 * instead. Use this directly only if you can't use `<Select>` itself
 * (e.g. composing with other custom markup around the element). */
export const selectClass = `${inputClass} appearance-none pr-9`;

/** Drop-in replacement for a bare `<select>` — same props, but with the
 * shared styling + a consistent chevron icon instead of whatever the
 * browser/WebView would otherwise draw. The open option list itself is
 * still native chrome (no way to skin that without a full custom
 * listbox), but the closed trigger now looks deliberate and matches every
 * other select in the app instead of varying page to page. */
export function Select({
  className = "",
  children,
  ...props
}: SelectHTMLAttributes<HTMLSelectElement>) {
  return (
    <div className={`relative ${className}`}>
      <select {...props} className={selectClass}>
        {children}
      </select>
      <svg
        aria-hidden="true"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2.5"
        strokeLinecap="round"
        strokeLinejoin="round"
        className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400 dark:text-gray-500"
      >
        <path d="m6 9 6 6 6-6" />
      </svg>
    </div>
  );
}
