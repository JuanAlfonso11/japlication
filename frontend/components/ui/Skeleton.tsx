/** Content-shaped loading placeholders.
 *
 * These replace the app's centered spinner on screens where we already know
 * the shape of what's coming (a swipe card, a list of applications, a job
 * detail). A skeleton in that shape makes the wait feel like the screen is
 * already assembling itself, and — unlike a spinner — it doesn't collapse
 * the layout and then shove it back into place when data lands.
 * The shimmer itself lives in `globals.css` (`.skeleton`). */

export function Skeleton({ className = "" }: { className?: string }) {
  return <div className={`skeleton ${className}`} />;
}

/** Home's swipe deck: one big card with the same rounding/inset padding as
 * the real `SwipeCard`, so nothing shifts when the queue arrives. */
export function SwipeCardSkeleton() {
  return (
    <div className="h-full w-full overflow-hidden rounded-3xl bg-white p-5 shadow-card ring-1 ring-gray-100 dark:bg-gray-900 dark:ring-gray-800">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1 space-y-2">
          <Skeleton className="h-5 w-3/4" />
          <Skeleton className="h-4 w-1/2" />
          <Skeleton className="h-3 w-1/3" />
        </div>
        <Skeleton className="h-14 w-14 shrink-0 rounded-full" />
      </div>
      <div className="mt-5 flex flex-wrap gap-1.5">
        {["w-16", "w-20", "w-12", "w-24", "w-14"].map((w, i) => (
          <Skeleton key={i} className={`h-6 rounded-full ${w}`} />
        ))}
      </div>
      <div className="mt-6 space-y-2">
        <Skeleton className="h-3 w-24" />
        <Skeleton className="h-3 w-full" />
        <Skeleton className="h-3 w-11/12" />
        <Skeleton className="h-3 w-4/5" />
      </div>
    </div>
  );
}

/** Generic stacked rows for list screens (Pipeline, Discover results). */
export function ListSkeleton({ rows = 4 }: { rows?: number }) {
  return (
    <div className="space-y-3">
      {Array.from({ length: rows }).map((_, i) => (
        <div
          key={i}
          className="rounded-2xl bg-white p-4 shadow-soft ring-1 ring-gray-100 dark:bg-gray-900 dark:ring-gray-800"
        >
          <div className="flex items-start justify-between gap-3">
            <div className="min-w-0 flex-1 space-y-2">
              <Skeleton className="h-4 w-2/3" />
              <Skeleton className="h-3 w-2/5" />
            </div>
            <Skeleton className="h-6 w-14 rounded-full" />
          </div>
        </div>
      ))}
    </div>
  );
}
