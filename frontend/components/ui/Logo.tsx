/** JobPilot's mark: a paper plane — "pilot", and an application in flight.
 *
 * Drawn inline as SVG rather than reusing `/icons/icon-192.png` (which the
 * header used to render at 28px) so it stays crisp at any size, needs no
 * network request, and can pick up the brand gradient from the same tokens
 * as the rest of the UI instead of being a baked-in bitmap that drifts
 * every time the palette changes.
 *
 * The two wings are the same white at different opacities: that fold is
 * what keeps the plane readable as a plane down at 20px, where a flat
 * silhouette turns into an unidentifiable triangle. */

export default function Logo({ className = "h-8 w-8" }: { className?: string }) {
  return (
    <svg viewBox="0 0 48 48" className={className} role="img" aria-label="JobPilot">
      <defs>
        <linearGradient id="jobpilot-mark" x1="0" y1="0" x2="1" y2="1">
          <stop offset="0%" stopColor="#9c79ff" />
          <stop offset="55%" stopColor="#6d28f5" />
          <stop offset="100%" stopColor="#4a1cad" />
        </linearGradient>
      </defs>
      <rect width="48" height="48" rx="13" fill="url(#jobpilot-mark)" />
      <path d="M37 12 L21.5 26.5 L26 37 Z" fill="#ffffff" fillOpacity="0.62" />
      <path d="M37 12 L11 22 L21.5 26.5 Z" fill="#ffffff" />
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
