/** JobPilot's mark: a compass needle inside a ring.
 *
 * "Pilot" is navigation, and the ring deliberately rhymes with the match
 * dial in `ScoreBadge` — the app's most-repeated shape. It replaced an
 * earlier paper plane, which read as a messaging app (Telegram owns that
 * silhouette) rather than anything to do with a job search.
 *
 * Painted with FLAT fills, no `<linearGradient>` + `url(#id)`. The gradient
 * version had a real bug: NavShell renders this twice (desktop header and
 * mobile header, one of them `display:none` at any given width) and both
 * copies declared the same gradient id. `url(#id)` resolves to the FIRST
 * match in document order — the hidden one — and a paint server inside a
 * `display:none` subtree paints nothing, so the logo silently vanished.
 * Verified in a standalone repro: duplicate id + hidden first copy renders
 * empty, unique id and flat fill both render fine. A flat fill can't
 * regress that way no matter how many times the component is mounted, and
 * at header sizes (28px) a gradient was imperceptible anyway. The generated
 * PNG icons — standalone files with no collision risk — do keep the
 * gradient, where it reads at 512px on a home screen. */

export default function Logo({ className = "h-8 w-8" }: { className?: string }) {
  return (
    <svg viewBox="0 0 48 48" className={className} role="img" aria-label="JobPilot">
      <rect width="48" height="48" rx="13" fill="#6d28f5" />
      <circle cx="24" cy="24" r="14" fill="none" stroke="#ffffff" strokeWidth="2.2" opacity="0.45" />
      {/* North half of the needle, bright; south half dimmed — that
          two-tone split is what makes it read as a compass rather than a
          generic arrow once it's down at 20px. */}
      <path d="M31.07 16.93 L26.83 26.83 L21.17 21.17 Z" fill="#ffffff" />
      <path d="M16.93 31.07 L26.83 26.83 L21.17 21.17 Z" fill="#ffffff" fillOpacity="0.45" />
    </svg>
  );
}

/** Mark + wordmark, for headers and the auth screens. */
export function Wordmark({
  className = "",
  markClassName = "h-8 w-8",
  textClassName = "text-[17px]",
}: {
  className?: string;
  markClassName?: string;
  textClassName?: string;
}) {
  return (
    <span className={`flex items-center gap-2 ${className}`}>
      <Logo className={markClassName} />
      <span
        className={`font-display font-extrabold tracking-display-tight text-gray-900 dark:text-gray-50 ${textClassName}`}
      >
        Job<span className="text-brand-600 dark:text-brand-400">Pilot</span>
      </span>
    </span>
  );
}
