"use client";

import Link from "next/link";
import { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import RouteGuard from "@/components/RouteGuard";
import Spinner from "@/components/Spinner";
import ErrorNotice from "@/components/ErrorNotice";
import StatusBadge, { STATUS_LABELS } from "@/components/StatusBadge";
import ScoreBadge from "@/components/ScoreBadge";
import { Select } from "@/components/ui/Field";
import { ApiError, applicationsApi } from "@/lib/api";
import type { Application, ApplicationStatus } from "@/lib/types";

const FILTERS: { value: ApplicationStatus | "all"; label: string }[] = [
  { value: "all", label: "All" },
  { value: "queued", label: STATUS_LABELS.queued },
  { value: "saved", label: STATUS_LABELS.saved },
  { value: "applied", label: STATUS_LABELS.applied },
  { value: "interviewing", label: STATUS_LABELS.interviewing },
  { value: "offer", label: STATUS_LABELS.offer },
  { value: "rejected", label: STATUS_LABELS.rejected },
  { value: "withdrawn", label: STATUS_LABELS.withdrawn },
];

const EDITABLE_STATUSES: ApplicationStatus[] = [
  "queued",
  "saved",
  "applied",
  "interviewing",
  "offer",
  "rejected",
  "withdrawn",
];

function ApplicationRow({
  application,
  onUpdated,
}: {
  application: Application;
  onUpdated: (app: Application) => void;
}) {
  const [expanded, setExpanded] = useState(false);
  const [notes, setNotes] = useState(application.notes ?? "");
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function updateStatus(status: ApplicationStatus) {
    setSaving(true);
    setError(null);
    try {
      const updated = await applicationsApi.update(application.id, { status });
      onUpdated(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not update status.");
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
      setError(err instanceof ApiError ? err.message : "Could not save notes.");
    } finally {
      setSaving(false);
    }
  }

  const job = application.job;

  return (
    <div className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-gray-100 dark:bg-gray-900 dark:ring-gray-800">
      <div className="flex items-start justify-between gap-3">
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          className="flex-1 text-left"
        >
          <p className="font-semibold text-gray-900 dark:text-gray-100">{job?.title ?? "Untitled job"}</p>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            {job?.company}
            {job?.location ? ` · ${job.location}` : ""}
          </p>
        </button>
        <div className="flex flex-col items-end gap-1.5">
          {job?.match && <ScoreBadge score={job.match.overall_score} size="sm" />}
          <StatusBadge status={application.status} />
        </div>
      </div>

      {expanded && (
        <div className="mt-4 space-y-3 border-t border-gray-100 pt-4 dark:border-gray-800">
          {error && <ErrorNotice message={error} />}
          <div className="flex flex-wrap items-center gap-2">
            <label className="text-xs font-medium text-gray-600 dark:text-gray-400" htmlFor={`status-${application.id}`}>
              Status
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
                View job →
              </Link>
            )}
          </div>

          <div>
            <label className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400" htmlFor={`notes-${application.id}`}>
              Notes
            </label>
            <textarea
              id={`notes-${application.id}`}
              value={notes}
              onChange={(e) => setNotes(e.target.value)}
              onBlur={() => {
                if (notes !== (application.notes ?? "")) saveNotes();
              }}
              placeholder="Interview prep notes, contacts, follow-ups…"
              className="min-h-[70px] w-full rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:focus:ring-brand-900/40"
            />
            <p className="mt-1 text-[11px] text-gray-400 dark:text-gray-500">
              {saving ? "Saving…" : "Notes save automatically when you click away."}
            </p>
          </div>
        </div>
      )}
    </div>
  );
}

function ApplicationsContent() {
  const searchParams = useSearchParams();
  const initialStatus = (searchParams.get("status") as ApplicationStatus | null) ?? "all";

  const [filter, setFilter] = useState<ApplicationStatus | "all">(initialStatus);
  const [applications, setApplications] = useState<Application[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const load = useCallback(async (status: ApplicationStatus | "all") => {
    setLoading(true);
    setError(null);
    try {
      const data = await applicationsApi.list(status === "all" ? undefined : status);
      setApplications(data);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load your applications.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load(filter);
  }, [filter, load]);

  function handleUpdated(updated: Application) {
    setApplications((prev) =>
      prev ? prev.map((a) => (a.id === updated.id ? { ...a, ...updated } : a)) : prev
    );
  }

  return (
    <div className="space-y-5 pb-4 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Applications</h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Track every job through your pipeline, from saved to offer.
        </p>
      </div>

      {/* Always wraps (never a hidden horizontal scroll) — with 8 filters,
          a scrollable single row cut off the last couple off-screen with
          no visual hint there was more to see. Wrapping keeps every
          filter visible up front, at the cost of taking 2-3 lines. */}
      <div className="flex flex-wrap gap-2 pt-1">
        {FILTERS.map((f) => (
          <button
            key={f.value}
            onClick={() => setFilter(f.value)}
            className={`rounded-full px-3.5 py-1.5 text-sm font-medium transition-colors ${
              filter === f.value
                ? "bg-brand-600 text-white"
                : "bg-white text-gray-600 ring-1 ring-gray-200 hover:bg-gray-50 dark:bg-gray-900 dark:text-gray-400 dark:ring-gray-700 dark:hover:bg-gray-800"
            }`}
          >
            {f.label}
          </button>
        ))}
      </div>

      {loading && <Spinner label="Loading applications…" />}
      {!loading && error && <ErrorNotice message={error} onRetry={() => load(filter)} />}

      {!loading && !error && applications && applications.length === 0 && (
        <div className="rounded-2xl border border-dashed border-gray-300 p-8 text-center text-sm text-gray-500 dark:border-gray-700 dark:text-gray-400">
          No applications in this view yet.
        </div>
      )}

      {!loading && !error && applications && applications.length > 0 && (
        <div className="space-y-3">
          {applications.map((app) => (
            <ApplicationRow key={app.id} application={app} onUpdated={handleUpdated} />
          ))}
        </div>
      )}
    </div>
  );
}

export default function ApplicationsPage() {
  return (
    <RouteGuard>
      <Suspense fallback={<Spinner label="Loading applications…" />}>
        <ApplicationsContent />
      </Suspense>
    </RouteGuard>
  );
}
