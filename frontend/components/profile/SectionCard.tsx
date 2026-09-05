export default function SectionCard({
  title,
  description,
  onAdd,
  addLabel = "Agregar",
  children,
}: {
  title: string;
  description?: string;
  onAdd?: () => void;
  addLabel?: string;
  children: React.ReactNode;
}) {
  return (
    <section className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-gray-100 dark:bg-gray-900 dark:ring-gray-800">
      <div className="mb-4 flex items-start justify-between gap-3">
        <div>
          <h2 className="font-semibold text-gray-900 dark:text-gray-100">{title}</h2>
          {description && <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">{description}</p>}
        </div>
        {onAdd && (
          <button
            type="button"
            onClick={onAdd}
            className="shrink-0 rounded-lg bg-brand-50 px-3 py-1.5 text-xs font-semibold text-brand-700 hover:bg-brand-100 dark:bg-brand-900/30 dark:text-brand-300 dark:hover:bg-brand-900/50"
          >
            + {addLabel}
          </button>
        )}
      </div>
      <div className="space-y-4">{children}</div>
    </section>
  );
}

export function EntryCard({
  onRemove,
  children,
}: {
  onRemove: () => void;
  children: React.ReactNode;
}) {
  return (
    <div className="relative rounded-xl border border-gray-200 p-4 dark:border-gray-700">
      <button
        type="button"
        onClick={onRemove}
        aria-label="Eliminar"
        className="absolute right-3 top-3 flex h-7 w-7 items-center justify-center rounded-full text-gray-400 hover:bg-gray-100 hover:text-rose-600 dark:text-gray-500 dark:hover:bg-gray-800 dark:hover:text-rose-400"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18M6 6l12 12" /></svg>
      </button>
      <div className="pr-8">{children}</div>
    </div>
  );
}
