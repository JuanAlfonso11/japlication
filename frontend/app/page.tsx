"use client";

import Link from "next/link";
import { useCallback, useEffect, useState } from "react";
import RouteGuard from "@/components/RouteGuard";
import Spinner from "@/components/Spinner";
import ErrorNotice from "@/components/ErrorNotice";
import StatusBadge from "@/components/StatusBadge";
import SwipeCard from "@/components/SwipeCard";
import { useAuth } from "@/context/AuthContext";
import { applicationsApi, ApiError, jobsApi } from "@/lib/api";
import type { Application, Job } from "@/lib/types";

const PIPELINE_STATUSES = ["applied", "interviewing", "offer"];

function StatsStrip({ applications, queueCount }: { applications: Application[]; queueCount: number }) {
  const counts = PIPELINE_STATUSES.reduce<Record<string, number>>((acc, status) => {
    acc[status] = applications.filter((a) => a.status === status).length;
    return acc;
  }, {});

  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      <div className="rounded-xl border border-gray-100 bg-white px-3 py-2.5 text-center shadow-sm">
        <p className="text-xl font-bold text-gray-900">{queueCount}</p>
        <p className="text-[11px] font-medium text-gray-500">in queue</p>
      </div>
      {PIPELINE_STATUSES.map((status) => (
        <Link
          key={status}
          href={`/applications?status=${status}`}
          className="rounded-xl border border-gray-100 bg-white px-3 py-2.5 text-center shadow-sm transition-colors hover:bg-gray-50"
        >
          <p className="text-xl font-bold text-gray-900">{counts[status]}</p>
          <div className="mt-0.5 flex justify-center">
            <StatusBadge status={status} />
          </div>
        </Link>
      ))}
    </div>
  );
}

function HomeContent() {
  const { user } = useAuth();
  const [queue, setQueue] = useState<Job[] | null>(null);
  const [applications, setApplications] = useState<Application[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const [matches, apps] = await Promise.all([
        jobsApi.matches({ limit: 50 }),
        applicationsApi.list(),
      ]);
      setQueue(matches.items);
      setApplications(apps);
    } catch (err) {
      setLoadError(err instanceof ApiError ? err.message : "Failed to load your recommendations.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const decide = useCallback(
    async (decision: "left" | "right") => {
      if (!queue || queue.length === 0 || pending) return;
      const current = queue[0];
      setPending(true);
      setActionError(null);
      try {
        await jobsApi.decide(current.id, { decision });
        setQueue((prev) => (prev ? prev.slice(1) : prev));
      } catch (err) {
        setActionError(
          err instanceof ApiError ? err.message : "Could not record your decision. Try again."
        );
      } finally {
        setPending(false);
      }
    },
    [queue, pending]
  );

  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === "ArrowRight") decide("right");
      if (e.key === "ArrowLeft") decide("left");
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [decide]);

  if (loading) return <Spinner label="Finding your best matches…" />;
  if (loadError) return <ErrorNotice message={loadError} onRetry={load} />;

  const current = queue && queue.length > 0 ? queue[0] : null;
  const next = queue && queue.length > 1 ? queue[1] : null;

  return (
    <div className="flex flex-col items-center gap-5 pb-4 animate-fade-in">
      <div className="w-full max-w-md">
        <h1 className="text-2xl font-bold text-gray-900">
          Hi{user?.full_name ? `, ${user.full_name.split(" ")[0]}` : ""} 👋
        </h1>
        <p className="mt-1 text-sm text-gray-500">
          Matches ranked against your CV. Swipe right to save, left to pass.
        </p>
      </div>

      {applications && <div className="w-full max-w-md"><StatsStrip applications={applications} queueCount={queue?.length ?? 0} /></div>}

      {actionError && (
        <div className="w-full max-w-md">
          <ErrorNotice message={actionError} />
        </div>
      )}

      <div className="relative h-[520px] w-full max-w-md">
        {!current && (
          <div className="flex h-full flex-col items-center justify-center gap-3 rounded-3xl border-2 border-dashed border-gray-300 p-8 text-center">
            <span className="text-4xl">🎉</span>
            <p className="text-lg font-semibold text-gray-800">You&apos;re all caught up</p>
            <p className="text-sm text-gray-500">
              No new recommendations right now. Discover more jobs to keep going.
            </p>
            <Link
              href="/discover"
              className="mt-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700"
            >
              Discover jobs
            </Link>
          </div>
        )}

        {next && <SwipeCard key={next.id} job={next} onDecide={() => {}} isTop={false} />}
        {current && <SwipeCard key={current.id} job={current} onDecide={decide} isTop={true} />}
      </div>

      {current && (
        <div className="flex items-center gap-6">
          <button
            type="button"
            onClick={() => decide("left")}
            disabled={pending}
            aria-label="Pass"
            className="flex h-14 w-14 items-center justify-center rounded-full bg-white text-rose-500 shadow-md ring-1 ring-gray-200 transition-transform hover:scale-105 active:scale-95 disabled:opacity-50"
          >
            <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18M6 6l12 12" /></svg>
          </button>
          <button
            type="button"
            onClick={() => decide("right")}
            disabled={pending}
            aria-label="Save"
            className="flex h-16 w-16 items-center justify-center rounded-full bg-emerald-500 text-white shadow-lg transition-transform hover:scale-105 active:scale-95 disabled:opacity-50"
          >
            <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M20 6 9 17l-5-5" /></svg>
          </button>
        </div>
      )}

      {queue && current && (
        <p className="text-xs text-gray-400">{queue.length} left in your queue</p>
      )}
    </div>
  );
}

export default function HomePage() {
  return (
    <RouteGuard>
      <HomeContent />
    </RouteGuard>
  );
}
