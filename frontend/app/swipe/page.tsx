"use client";

import { useCallback, useEffect, useState } from "react";
import Link from "next/link";
import RouteGuard from "@/components/RouteGuard";
import Spinner from "@/components/Spinner";
import ErrorNotice from "@/components/ErrorNotice";
import SwipeCard from "@/components/SwipeCard";
import { ApiError, jobsApi } from "@/lib/api";
import type { Job } from "@/lib/types";

function SwipeContent() {
  const [queue, setQueue] = useState<Job[] | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [pending, setPending] = useState(false);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const res = await jobsApi.matches({ limit: 50 });
      setQueue(res.items);
    } catch (err) {
      setLoadError(err instanceof ApiError ? err.message : "Failed to load your match queue.");
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
    <div className="flex flex-col items-center gap-4 pb-4 animate-fade-in">
      <div className="w-full max-w-md text-center">
        <h1 className="text-2xl font-bold text-gray-900">Swipe your matches</h1>
        <p className="mt-1 text-sm text-gray-500">
          Swipe right to save, left to pass. Arrow keys work too.
        </p>
      </div>

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
              No more matches in your queue right now. Import more jobs to keep going.
            </p>
            <Link
              href="/jobs/import"
              className="mt-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700"
            >
              Import a job
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

export default function SwipePage() {
  return (
    <RouteGuard>
      <SwipeContent />
    </RouteGuard>
  );
}
