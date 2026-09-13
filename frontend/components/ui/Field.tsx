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
  /** Usually a string; ReactNode so a label can carry a small badge next to
   * it (Respuestas marks the unanswered ones this way). */
  label: ReactNode;
  children: ReactNode;
  className?: string;
}) {
  return (
    <label className={`block ${className}`}>
      <span className="mb-1.5 block text-xs font-semibold text-gray-600 dark:text-gray-400">{label}</span>
      {children}
    </label>
  );
}

/* min-h-[46px] rather than a `py` value: it holds the same comfortable tap
 * height whether the control is an input, a select, or wraps to two lines,
 * which is what kept the old py-2/py-2.5/py-1.5 mix from ever lining up.
 * The focus ring is a shadow, not `ring-*`, so it composes with the
 * border-color change instead of fighting it for the same pixels. */
export const inputClass =
  "w-full min-h-[46px] rounded-xl border border-gray-200 bg-white px-3.5 text-sm text-gray-900 outline-none transition-all placeholder:text-gray-400 hover:border-gray-300 focus:border-brand-500 focus:shadow-[0_0_0_3px_rgb(109_40_245_/_0.12)] dark:border-gray-700 dark:bg-gray-800/60 dark:text-gray-100 dark:placeholder:text-gray-500 dark:hover:border-gray-600 dark:focus:border-brand-400 dark:focus:shadow-[0_0_0_3px_rgb(156_121_255_/_0.18)]";

export const textareaClass = `${inputClass} min-h-[88px] resize-y py-2.5 leading-relaxed`;

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
        className="pointer-events-none absolute right-3 top-1/2 h-4 w-4 -translate-y-1/2 text-gray-400 dark:text-gray-400"
      >
        <path d="m6 9 6 6 6-6" />
      </svg>
    </div>
  );
}
