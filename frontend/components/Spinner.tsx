/** Indeterminate loader for the few places where the shape of what's
 * coming isn't known ahead of time (an import that may or may not return a
 * job, a route-level Suspense boundary). Screens that *do* know the shape
 * should use the skeletons in `components/ui/Skeleton.tsx` instead. */
export default function Spinner({ label }: { label?: string }) {
  return (
    <div
      role="status"
      className="flex min-h-[40vh] flex-col items-center justify-center gap-3 text-gray-500 dark:text-gray-400"
    >
      <div className="h-8 w-8 animate-spin rounded-full border-[3px] border-gray-200 border-t-brand-600 dark:border-gray-800 dark:border-t-brand-400" />
      {label && <p className="text-sm font-medium">{label}</p>}
    </div>
  );
}
