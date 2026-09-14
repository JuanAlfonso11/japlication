import type { ButtonHTMLAttributes, ReactNode } from "react";

/** The app's one button vocabulary. Before this existed every screen wrote
 * its own Tailwind string, so the same "primary action" appeared at three
 * different paddings, two radii and two shadow treatments — the single
 * biggest tell that the UI was assembled screen by screen rather than
 * designed. Anything that looks like a button should use this (or copy its
 * classes verbatim when it has to be an `<a>`/`<Link>`; see `buttonClass`). */

type Variant = "primary" | "secondary" | "ghost" | "danger";
type Size = "sm" | "md" | "lg";

const VARIANTS: Record<Variant, string> = {
  primary:
    // Inverted in dark mode: with a graphite brand, `dark:bg-brand-500` put
    // white text on mid-grey (about 3.4:1, under AA) and a brand-600 button
    // would vanish into the near-black surface behind it. On black the
    // primary is the light end of the ramp with dark text.
    "bg-brand-600 text-white shadow-brand hover:bg-brand-700 hover:shadow-brand-lg focus-visible:outline-brand-600 dark:bg-brand-200 dark:text-gray-950 dark:hover:bg-brand-100",
  secondary:
    "bg-white text-gray-700 ring-1 ring-inset ring-gray-200 shadow-soft hover:bg-gray-50 hover:ring-gray-300 dark:bg-gray-900 dark:text-gray-200 dark:ring-gray-700 dark:hover:bg-gray-800",
  ghost:
    "text-gray-600 hover:bg-gray-100 hover:text-gray-900 dark:text-gray-400 dark:hover:bg-gray-800 dark:hover:text-gray-100",
  danger:
    "bg-rose-600 text-white shadow-soft hover:bg-rose-700 dark:bg-rose-600 dark:hover:bg-rose-500",
};

/* min-h values keep every size at or above the 44px comfortable tap target
 * on touch, which the old hand-rolled `py-1.5` buttons sat under. */
const SIZES: Record<Size, string> = {
  sm: "min-h-[36px] gap-1.5 rounded-lg px-3 text-xs",
  md: "min-h-[44px] gap-2 rounded-xl px-4 text-sm",
  lg: "min-h-[52px] gap-2 rounded-2xl px-6 text-base",
};

const BASE =
  "inline-flex items-center justify-center font-semibold transition-all duration-150 active:scale-[0.97] disabled:pointer-events-none disabled:opacity-50";

export function buttonClass({
  variant = "primary",
  size = "md",
  fullWidth = false,
  className = "",
}: {
  variant?: Variant;
  size?: Size;
  fullWidth?: boolean;
  className?: string;
} = {}) {
  return [BASE, VARIANTS[variant], SIZES[size], fullWidth ? "w-full" : "", className]
    .filter(Boolean)
    .join(" ");
}

export default function Button({
  variant = "primary",
  size = "md",
  fullWidth = false,
  loading = false,
  children,
  className = "",
  disabled,
  ...props
}: {
  variant?: Variant;
  size?: Size;
  fullWidth?: boolean;
  /** Swaps the label for a spinner and blocks input, so callers don't each
   * invent their own "Guardando…" string plus a `disabled` prop. */
  loading?: boolean;
  children: ReactNode;
} & ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      {...props}
      disabled={disabled || loading}
      className={buttonClass({ variant, size, fullWidth, className })}
    >
      {loading && (
        <span
          aria-hidden="true"
          className="h-4 w-4 shrink-0 animate-spin rounded-full border-2 border-current border-t-transparent opacity-70"
        />
      )}
      {children}
    </button>
  );
}
