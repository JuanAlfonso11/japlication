"use client";

import Link from "next/link";
import { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import RouteGuard from "@/components/RouteGuard";
import ErrorNotice from "@/components/ErrorNotice";
import StatusBadge, { STATUS_LABELS } from "@/components/StatusBadge";
import ScoreBadge from "@/components/ScoreBadge";
import { Select, textareaClass } from "@/components/ui/Field";
import Button from "@/components/ui/Button";
import { ListSkeleton } from "@/components/ui/Skeleton";
import PageHeader from "@/components/ui/PageHeader";
import { ApiError, applicationsApi } from "@/lib/api";
import type { Application, ApplicationStatus } from "@/lib/types";

/** "Activas" is everything still in play and is what this screen opens on:
 * with 120 discarded jobs in the table, "Todas" first shows a wall of
 * decisions that are already over and buries the ones being chased. */
type Filter = ApplicationStatus | "all" | "active";

const FILTERS: { value: Filter; label: string }[] = [
  { value: "active", label: "Activas" },
  { value: "all", label: "Todas" },
  { value: "queued", label: STATUS_LABELS.queued },
  { value: "saved", label: STATUS_LABELS.saved },
  { value: "applied", label: STATUS_LABELS.applied },
  { value: "interviewing", label: STATUS_LABELS.interviewing },
  { value: "offer", label: STATUS_LABELS.offer },
  { value: "passed", label: STATUS_LABELS.passed },
  { value: "rejected", label: STATUS_LABELS.rejected },
  { value: "withdrawn", label: STATUS_LABELS.withdrawn },
];

const PAGE_SIZE = 50;

/** Every status the dropdown can show, "passed" included: leaving it out
 * made a discarded row display the *first* option ("En cola") instead of
 * its real status, one tap away from silently reviving it. */
const EDITABLE_STATUSES: ApplicationStatus[] = [
  "queued",
  "saved",
  "applied",
  "interviewing",
  "offer",
  "passed",
  "rejected",
  "withdrawn",
];

function ApplicationRow({
  application,
  onUpdated,
  onUndone,
}: {
  application: Application;
  onUpdated: (app: Application) => void;
  onUndone: (id: string) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [notes, setNotes] = useState(application.notes ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [undoing, setUndoing] = useState(false);
  // The status dropdown saves the moment it changes, with no confirmation —
  // so the previous value is kept here to offer one tap back.
  const [previousStatus, setPreviousStatus] = useState<ApplicationStatus | null>(null);

  async function handleUndo() {
    setUndoing(true);
    setError(null);
    try {
      await applicationsApi.undo(application.id);
      onUndone(application.id);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo deshacer.");
      setUndoing(false);
    }
  }

  async function updateStatus(status: ApplicationStatus, isUndo = false) {
    const before = application.status;
    setSaving(true);
    setError(null);
    try {
      const updated = await applicationsApi.update(application.id, { status });
      onUpdated(updated);
      setPreviousStatus(isUndo ? null : before);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo actualizar el estado.");
    } finally {
      setSaving(false);
    }
  }

  async function saveNotes() {
    setSaving(true);
    setError(null);
    try {
      const updated = await applicationsApi.update(application.id, { notes });
      onUpdated(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudieron guardar las notas.");
    } finally {
      setSaving(false);
    }
  }

  const job = application.job;

  return (
    <div
      className={`rounded-2xl bg-white p-3.5 ring-1 transition-shadow dark:bg-gray-900 ${
        expanded
          ? "shadow-card ring-gray-200 dark:ring-gray-700"
          : "shadow-soft ring-gray-100 hover:shadow-card dark:ring-gray-800"
      }`}
    >
      <div className="flex items-start justify-between gap-3">
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
          className="flex min-w-0 flex-1 items-start gap-3 text-left"
        >
          <span
            aria-hidden="true"
            className="mt-0.5 flex h-9 w-9 shrink-0 items-center justify-center rounded-lg bg-gray-100 font-display text-sm font-extrabold text-gray-500 dark:bg-gray-800 dark:text-gray-400"
          >
            {job?.company?.trim()?.[0]?.toUpperCase() ?? "?"}
          </span>
          <span className="min-w-0 flex-1">
            {/* Two lines, not one truncated one: at this width a single line
                cut "Backend Software Engineer" down to "Backend Software …"
                on every row, so different jobs read as duplicates. */}
            <span className="line-clamp-2 font-semibold text-gray-900 dark:text-gray-100">
              {job?.title ?? "Trabajo sin título"}
            </span>
            <span className="mt-0.5 block truncate text-[13px] text-gray-500 dark:text-gray-400">
              {job?.company}
              {job?.location ? ` · ${job.location}` : ""}
            </span>
          </span>
          <svg
            aria-hidden="true"
            width="16"
            height="16"
            viewBox="0 0 24 24"
            fill="none"
            stroke="currentColor"
            strokeWidth="2.5"
            strokeLinecap="round"
            strokeLinejoin="round"
            className={`mt-2 shrink-0 text-gray-300 transition-transform dark:text-gray-600 ${
              expanded ? "rotate-180" : ""
            }`}
          >
            <path d="m6 9 6 6 6-6" />
          </svg>
        </button>
        <div className="flex shrink-0 flex-col items-end gap-1.5">
          {job?.match && <ScoreBadge score={job.match.overall_score} size="sm" />}
          <StatusBadge status={application.status} />
          {application.status === "passed" && (
            <button
              type="button"
              onClick={handleUndo}
              disabled={undoing}
              className="text-[11px] font-bold text-brand-600 hover:underline disabled:opacity-60 dark:text-brand-400"
            >
              {undoing ? "Deshaciendo…" : "Deshacer"}
            </button>
          )}
        </div>
      </div>

      {error && (
        <div className="mt-2">
          <ErrorNotice message={error} />
        </div>
      )}

      {previousStatus && (
        <div className="mt-2 flex items-center justify-between gap-2 rounded-xl bg-gray-900 px-3 py-1.5 dark:bg-gray-800">
          <p className="min-w-0 truncate text-[11px] text-gray-300">
            Movida a <strong className="font-semibold text-white">{STATUS_LABELS[application.status]}</strong>
          </p>
          <button
            type="button"
            onClick={() => updateStatus(previousStatus, true)}
            disabled={saving}
            className="shrink-0 text-[11px] font-bold text-white hover:underline disabled:opacity-60"
          >
            Deshacer
          </button>
        </div>
      )}

      {expanded && (
        <div className="mt-4 space-y-3 border-t border-gray-100 pt-4 dark:border-gray-800">
          <div className="flex flex-wrap items-center gap-2">
            <label className="text-xs font-medium text-gray-600 dark:text-gray-400" htmlFor={`status-${application.id}`}>
              Estado
            </label>
            <Select
              id={`status-${application.id}`}
              value={application.status}
              disabled={saving}
              onChange={(e) => updateStatus(e.target.value as ApplicationStatus)}
              className="w-44"
            >
              {EDITABLE_STATUSES.map((s) => (
                <option key={s} value={s}>
                  {STATUS_LABELS[s]}
                </option>
              ))}
            </Select>
            {job && (
              <Link
                href={`/jobs/${job.id}`}
                className="ml-auto text-xs font-semibold text-brand-600 hover:text-brand-700 dark:text-brand-400 dark:hover:text-brand-300"
              >
                Ver trabajo →
              </Link>
            )}
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400" htmlFor={`notes-${application.id}`}>
              Notas
            </label>
            <textarea
              id={`notes-${application.id}`}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              onBlur={() => {
                if (notes !== (application.notes ?? "")) saveNotes();
              }}
              placeholder="Notas de la entrevista, contactos, seguimientos…"
              className={textareaClass}
            />
            <p className="mt-1 text-[11px] text-gray-400 dark:text-gray-400">
              {saving ? "Guardando…" : "Las notas se guardan solas al salir del campo."}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

function ApplicationsContent() {
  const searchParams = useSearchParams();
  const initialStatus = (searchParams.get("status") as ApplicationStatus | null) ?? "active";

  const [filter, setFilter] = useState<Filter>(initialStatus);
  const [applications, setApplications] = useState<Application[] | null>(null);
  const [total, setTotal] = useState(0);
  const [loading, setLoading] = useState(true);
  const [loadingMore, setLoadingMore] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (status: Filter) => {
    setLoading(true);
    setError(null);
    try {
      const data = await applicationsApi.list(
        status === "all" || status === "active" ? undefined : status,
        PAGE_SIZE,
        0,
        status === "active"
      );
      setApplications(data.items);
      setTotal(data.total);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudieron cargar tus aplicaciones.");
    } finally {
      setLoading(false);
    }
  }, []);

  async function loadMore() {
    if (!applications) return;
    setLoadingMore(true);
    try {
      const data = await applicationsApi.list(
        filter === "all" || filter === "active" ? undefined : filter,
        PAGE_SIZE,
        applications.length,
        filter === "active"
      );
      setApplications((prev) => (prev ? [...prev, ...data.items] : data.items));
      setTotal(data.total);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudieron cargar más aplicaciones.");
    } finally {
      setLoadingMore(false);
    }
  }

  useEffect(() => {
    load(filter);
  }, [filter, load]);

  function handleUpdated(updated: Application) {
    setApplications((prev) =>
      prev ? prev.map((a) => (a.id === updated.id ? { ...a, ...updated } : a)) : prev
    );
  }

  function handleUndone(id: string) {
    setApplications((prev) => (prev ? prev.filter((a) => a.id !== id) : prev));
    setTotal((prev) => Math.max(0, prev - 1));
  }

  return (
    <div className="space-y-5 pb-4 animate-fade-in">
      <PageHeader
        title="Pipeline"
        subtitle="Sigue cada trabajo desde guardado hasta oferta."
        action={
          !loading && !error && applications ? (
            <span className="tabular inline-flex items-center rounded-full bg-gray-100 px-3 py-1.5 text-xs font-bold text-gray-600 dark:bg-gray-800 dark:text-gray-300">
              {total} en total
            </span>
          ) : null
        }
      />

      {/* Always wraps (never a hidden horizontal scroll) — with these
          filters, a scrollable single row cut off the last couple
          off-screen with no visual hint there was more to see. Wrapping
          keeps every filter visible up front, at the cost of taking 2-3
          lines. */}
      <div className="flex flex-wrap gap-1.5 pt-1">
        {FILTERS.map((f) => (
          <button
            key={f.value}
            onClick={() => setFilter(f.value)}
            aria-pressed={filter === f.value}
            className={`min-h-[34px] rounded-full px-3.5 text-[13px] font-semibold transition-all active:scale-95 ${
              filter === f.value
                ? "bg-brand-600 dark:bg-brand-200 dark:text-gray-950 text-white shadow-brand"
                : "bg-white text-gray-600 ring-1 ring-inset ring-gray-200 hover:bg-gray-50 hover:text-gray-900 dark:bg-gray-900 dark:text-gray-400 dark:ring-gray-700 dark:hover:bg-gray-800"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {loading && <ListSkeleton rows={5} />}
      {!loading && error && <ErrorNotice message={error} onRetry={() => load(filter)} />}

      {!loading && !error && applications && applications.length === 0 && (
        <div className="rounded-3xl bg-white/60 p-10 text-center ring-1 ring-inset ring-gray-200 dark:bg-gray-900/40 dark:ring-gray-800">
          <span className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-2xl bg-brand-50 text-brand-600 dark:bg-brand-500/15 dark:text-brand-400">
            <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
              <rect x="3" y="4" width="18" height="4" rx="1" />
              <rect x="3" y="10" width="12" height="4" rx="1" />
              <rect x="3" y="16" width="8" height="4" rx="1" />
            </svg>
          </span>
          <p className="font-display text-base font-extrabold text-gray-900 dark:text-gray-100">
            Nada por aquí todavía
          </p>
          <p className="mx-auto mt-1 max-w-[38ch] text-sm text-gray-500 dark:text-gray-400">
            {filter === "all" || filter === "active"
              ? "Cuando guardes una vacante desde Inicio, aparecerá en esta lista."
              : `No tienes vacantes en "${FILTERS.find((f) => f.value === filter)?.label}".`}
          </p>
        </div>
      )}

      {!loading && !error && applications && applications.length > 0 && (
        <div className="space-y-2.5">
          {applications.map((app) => (
            <ApplicationRow key={app.id} application={app} onUpdated={handleUpdated} onUndone={handleUndone} />
          ))}
          {applications.length < total && (
            <div className="flex justify-center pt-2">
              <Button variant="secondary" onClick={loadMore} loading={loadingMore}>
                {loadingMore ? "Cargando…" : `Cargar más (${total - applications.length} restantes)`}
              </Button>
            </div>
          )}
        </div>
      )}
    </div>
  );
}

export default function ApplicationsPage() {
  return (
    <RouteGuard>
      <Suspense fallback={<ListSkeleton rows={5} />}>
        <ApplicationsContent />
      </Suspense>
    </RouteGuard>
  );
}
