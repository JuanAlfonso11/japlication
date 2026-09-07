export default function ErrorNotice({
  message,
  onRetry,
}: {
  message: string;
  onRetry?: () => void;
}) {
  return (
    <div
      role="alert"
      className="flex gap-3 rounded-2xl bg-rose-50 p-4 text-sm ring-1 ring-inset ring-rose-200 dark:bg-rose-500/10 dark:ring-rose-500/25"
    >
      <span className="mt-0.5 flex h-6 w-6 shrink-0 items-center justify-center rounded-full bg-rose-100 text-rose-600 dark:bg-rose-500/20 dark:text-rose-300">
        <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round">
          <path d="M12 8v5" />
          <path d="M12 17h.01" />
        </svg>
      </span>
      <div className="min-w-0 flex-1">
        <p className="font-bold text-rose-800 dark:text-rose-200">Algo salió mal</p>
        <p className="mt-0.5 leading-relaxed text-rose-700 dark:text-rose-300">{message}</p>
        {onRetry && (
          <button
            onClick={onRetry}
            className="mt-3 inline-flex min-h-[34px] items-center rounded-lg bg-rose-600 px-3.5 text-xs font-bold text-white transition-colors hover:bg-rose-700 active:scale-95"
          >
            Reintentar
          </button>
        )}
      </div>
    </div>
  );
}
