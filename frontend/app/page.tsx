"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import RouteGuard from "@/components/RouteGuard";
import Spinner from "@/components/Spinner";
import ErrorNotice from "@/components/ErrorNotice";
import StatusBadge from "@/components/StatusBadge";
import { useAuth } from "@/context/AuthContext";
import { applicationsApi, ApiError, jobsApi } from "@/lib/api";
import type { Application } from "@/lib/types";

const PIPELINE_STATUSES = [
  "saved",
  "applied",
  "interviewing",
  "offer",
  "rejected",
  "withdrawn",
];

function HomeContent() {
  const { user } = useAuth();
  const [applications, setApplications] = useState<Application[] | null>(null);
  const [queueCount, setQueueCount] = useState<number | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  async function load() {
    setLoading(true);
    setError(null);
    try {
      const [apps, matches] = await Promise.all([
        applicationsApi.list(),
        jobsApi.matches({ limit: 50 }),
      ]);
      setApplications(apps);
      setQueueCount(matches.items.length);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load your dashboard.");
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  if (loading) return <Spinner label="Loading your dashboard…" />;
  if (error) return <ErrorNotice message={error} onRetry={load} />;

  const counts = PIPELINE_STATUSES.reduce<Record<string, number>>((acc, status) => {
    acc[status] = applications?.filter((a) => a.status === status).length ?? 0;
    return acc;
  }, {});

  return (
    <div className="space-y-6 pb-4 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">
          Hi{user?.full_name ? `, ${user.full_name.split(" ")[0]}` : ""} 👋
        </h1>
        <p className="mt-1 text-sm text-gray-500">Here&apos;s where your search stands today.</p>
      </div>

      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
        <Link
          href="/swipe"
          className="group relative overflow-hidden rounded-2xl bg-brand-600 p-5 text-white shadow-sm transition-transform hover:-translate-y-0.5"
        >
          <p className="text-sm font-medium text-brand-100">Ready to review</p>
          <p className="mt-1 text-3xl font-bold">{queueCount ?? 0}</p>
          <p className="mt-1 text-sm text-brand-100">
            {queueCount ? "new matches waiting in your swipe queue" : "no new matches right now"}
          </p>
          <span className="mt-3 inline-flex items-center gap-1 text-sm font-semibold">
            Go to Swipe
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14M13 5l7 7-7 7" /></svg>
          </span>
        </Link>

        <Link
          href="/jobs/import"
          className="group relative overflow-hidden rounded-2xl bg-white p-5 shadow-sm ring-1 ring-gray-100 transition-transform hover:-translate-y-0.5"
        >
          <p className="text-sm font-medium text-gray-500">Add a job</p>
          <p className="mt-1 text-xl font-bold text-gray-900">Import a posting</p>
          <p className="mt-1 text-sm text-gray-500">Paste a URL or description to get matched.</p>
          <span className="mt-3 inline-flex items-center gap-1 text-sm font-semibold text-brand-600">
            Import a job
            <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14M13 5l7 7-7 7" /></svg>
          </span>
        </Link>
      </div>

      <div className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-gray-100">
        <div className="mb-4 flex items-center justify-between">
          <h2 className="font-semibold text-gray-900">Pipeline overview</h2>
          <Link href="/applications" className="text-sm font-semibold text-brand-600 hover:text-brand-700">
            View all
          </Link>
        </div>
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-6">
          {PIPELINE_STATUSES.map((status) => (
            <Link
              key={status}
              href={`/applications?status=${status}`}
              className="flex flex-col items-center gap-1.5 rounded-xl border border-gray-100 bg-gray-50 px-2 py-3 text-center transition-colors hover:bg-gray-100"
            >
              <span className="text-2xl font-bold text-gray-900">{counts[status]}</span>
              <StatusBadge status={status} />
            </Link>
          ))}
        </div>
      </div>

      {applications && applications.length === 0 && (
        <div className="rounded-2xl border border-dashed border-gray-300 p-6 text-center text-sm text-gray-500">
          No applications yet. Import a job posting, then swipe right on the ones you like to
          start your pipeline.
        </div>
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
