"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useState } from "react";
import RouteGuard from "@/components/RouteGuard";
import Spinner from "@/components/Spinner";
import ErrorNotice from "@/components/ErrorNotice";
import StatusBadge from "@/components/StatusBadge";
import SwipeCard from "@/components/SwipeCard";
import { useAuth } from "@/context/AuthContext";
import { applicationsApi, ApiError, jobsApi } from "@/lib/api";
import {
  detectUserLocation,
  jobMatchesScope,
  loadCachedLocation,
  SCOPE_LEVELS,
  type UserLocation,
} from "@/lib/geoScope";
import type { Application, Job } from "@/lib/types";

const PIPELINE_STATUSES = ["applied", "interviewing", "offer"];
const DEFAULT_SCOPE_INDEX = SCOPE_LEVELS.length - 1; // "Cualquier lugar" — never hides jobs by default

function ScopeSlider({
  scopeIndex,
  onChange,
  geoStatus,
  geoError,
  userLocation,
}: {
  scopeIndex: number;
  onChange: (index: number) => void;
  geoStatus: "idle" | "locating" | "granted" | "denied";
  geoError: string | null;
  userLocation: UserLocation | null;
}) {
  const locationText = userLocation
    ? [userLocation.city, userLocation.region, userLocation.country].filter(Boolean).join(", ")
    : null;

  return (
    <div className="w-full max-w-md rounded-xl border border-gray-100 bg-white p-3 shadow-sm dark:border-gray-800 dark:bg-gray-900">
      <div className="flex items-center justify-between">
        <span className="text-xs font-semibold text-gray-700 dark:text-gray-300">
          📍 Alcance: {SCOPE_LEVELS[scopeIndex].label}
        </span>
        {geoStatus === "locating" && (
          <span className="text-[11px] text-gray-400 dark:text-gray-500">Ubicando…</span>
        )}
      </div>
      <input
        type="range"
        min={0}
        max={SCOPE_LEVELS.length - 1}
        step={1}
        value={scopeIndex}
        onChange={(e) => onChange(Number(e.target.value))}
        className="mt-2 w-full accent-brand-600"
      />
      <div className="mt-1 flex justify-between text-[9px] leading-tight text-gray-400 dark:text-gray-500">
        {SCOPE_LEVELS.map((lvl) => (
          <span key={lvl.scope} className="w-12 text-center first:text-left last:text-right">
            {lvl.label}
          </span>
        ))}
      </div>
      {geoStatus === "denied" && geoError && (
        <p className="mt-1.5 text-[11px] text-rose-500 dark:text-rose-400">
          {geoError} Activa el permiso de ubicación en tu navegador o elige &quot;Cualquier lugar&quot;.
        </p>
      )}
      {locationText && (
        <p className="mt-1.5 text-[11px] text-gray-400 dark:text-gray-500">Tu ubicación: {locationText}</p>
      )}
    </div>
  );
}

function StatsStrip({ applications, queueCount }: { applications: Application[]; queueCount: number }) {
  const counts = PIPELINE_STATUSES.reduce<Record<string, number>>((acc, status) => {
    acc[status] = applications.filter((a) => a.status === status).length;
    return acc;
  }, {});

  return (
    <div className="grid grid-cols-2 gap-2 sm:grid-cols-4">
      <div className="rounded-xl border border-gray-100 bg-white px-3 py-2.5 text-center shadow-sm dark:border-gray-800 dark:bg-gray-900">
        <p className="text-xl font-bold text-gray-900 dark:text-gray-100">{queueCount}</p>
        <p className="text-[11px] font-medium text-gray-500 dark:text-gray-400">in queue</p>
      </div>
      {PIPELINE_STATUSES.map((status) => (
        <Link
          key={status}
          href={`/applications?status=${status}`}
          className="rounded-xl border border-gray-100 bg-white px-3 py-2.5 text-center shadow-sm transition-colors hover:bg-gray-50 dark:border-gray-800 dark:bg-gray-900 dark:hover:bg-gray-800"
        >
          <p className="text-xl font-bold text-gray-900 dark:text-gray-100">{counts[status]}</p>
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

  const [scopeIndex, setScopeIndex] = useState(DEFAULT_SCOPE_INDEX);
  const [userLocation, setUserLocation] = useState<UserLocation | null>(null);
  const [geoStatus, setGeoStatus] = useState<"idle" | "locating" | "granted" | "denied">("idle");
  const [geoError, setGeoError] = useState<string | null>(null);

  useEffect(() => {
    const cached = loadCachedLocation();
    if (cached) {
      setUserLocation(cached);
      setGeoStatus("granted");
    }
  }, []);

  const handleScopeChange = useCallback(
    (index: number) => {
      setScopeIndex(index);
      const scope = SCOPE_LEVELS[index].scope;
      if (scope === "remote" || scope === "any") return;
      if (userLocation || geoStatus === "locating") return;

      setGeoStatus("locating");
      setGeoError(null);
      detectUserLocation()
        .then((loc) => {
          setUserLocation(loc);
          setGeoStatus("granted");
        })
        .catch((err) => {
          setGeoStatus("denied");
          setGeoError(err instanceof Error ? err.message : "No se pudo obtener tu ubicación.");
        });
    },
    [userLocation, geoStatus]
  );

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

  const scope = SCOPE_LEVELS[scopeIndex].scope;
  const filteredQueue = useMemo(
    () => (queue ? queue.filter((job) => jobMatchesScope(job, scope, userLocation)) : null),
    [queue, scope, userLocation]
  );
  const current = filteredQueue && filteredQueue.length > 0 ? filteredQueue[0] : null;
  const next = filteredQueue && filteredQueue.length > 1 ? filteredQueue[1] : null;

  // Set only by the ✓/✕ buttons and arrow keys, to trigger the same
  // fly-off exit animation a drag gesture produces. The drag gesture
  // triggers its own exit internally and calls `decide` directly once the
  // animation finishes, so this stays null in that path.
  const [pendingDecision, setPendingDecision] = useState<"left" | "right" | null>(null);

  const decide = useCallback(
    async (decision: "left" | "right") => {
      if (!current || pending) return;
      const target = current;
      setPending(true);
      setActionError(null);
      try {
        await jobsApi.decide(target.id, { decision });
        setQueue((prev) => (prev ? prev.filter((j) => j.id !== target.id) : prev));
      } catch (err) {
        setActionError(
          err instanceof ApiError ? err.message : "Could not record your decision. Try again."
        );
      } finally {
        setPending(false);
        setPendingDecision(null);
      }
    },
    [current, pending]
  );

  const requestDecision = useCallback(
    (decision: "left" | "right") => {
      if (!current || pending || pendingDecision) return;
      setPendingDecision(decision);
    },
    [current, pending, pendingDecision]
  );

  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      if (e.key === "ArrowRight") requestDecision("right");
      if (e.key === "ArrowLeft") requestDecision("left");
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [requestDecision]);

  if (loading) return <Spinner label="Finding your best matches…" />;
  if (loadError) return <ErrorNotice message={loadError} onRetry={load} />;

  const hiddenByScope = (queue?.length ?? 0) > 0 && (filteredQueue?.length ?? 0) === 0;

  return (
    <div className="flex flex-col items-center gap-5 pb-4 animate-fade-in">
      <div className="w-full max-w-md">
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">
          Hi{user?.full_name ? `, ${user.full_name.split(" ")[0]}` : ""} 👋
        </h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Matches ranked against your CV. Swipe right to save, left to pass.
        </p>
      </div>

      <ScopeSlider
        scopeIndex={scopeIndex}
        onChange={handleScopeChange}
        geoStatus={geoStatus}
        geoError={geoError}
        userLocation={userLocation}
      />

      {applications && <div className="w-full max-w-md"><StatsStrip applications={applications} queueCount={filteredQueue?.length ?? 0} /></div>}

      {actionError && (
        <div className="w-full max-w-md">
          <ErrorNotice message={actionError} />
        </div>
      )}

      <div className="relative h-[520px] w-full max-w-md">
        {!current && hiddenByScope && (
          <div className="flex h-full flex-col items-center justify-center gap-3 rounded-3xl border-2 border-dashed border-gray-300 p-8 text-center dark:border-gray-700">
            <span className="text-4xl">📍</span>
            <p className="text-lg font-semibold text-gray-800 dark:text-gray-200">Nada en este alcance</p>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              Hay recomendaciones esperando, pero ninguna coincide con &quot;
              {SCOPE_LEVELS[scopeIndex].label}&quot;. Prueba un alcance más amplio.
            </p>
            <button
              type="button"
              onClick={() => setScopeIndex(DEFAULT_SCOPE_INDEX)}
              className="mt-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700"
            >
              Ver cualquier lugar
            </button>
          </div>
        )}

        {!current && !hiddenByScope && (
          <div className="flex h-full flex-col items-center justify-center gap-3 rounded-3xl border-2 border-dashed border-gray-300 p-8 text-center dark:border-gray-700">
            <span className="text-4xl">🎉</span>
            <p className="text-lg font-semibold text-gray-800 dark:text-gray-200">You&apos;re all caught up</p>
            <p className="text-sm text-gray-500 dark:text-gray-400">
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
        {current && (
          <SwipeCard
            key={current.id}
            job={current}
            onDecide={decide}
            isTop={true}
            triggerExit={pendingDecision}
          />
        )}
      </div>

      {current && (
        <div className="flex items-center gap-6">
          <button
            type="button"
            onClick={() => requestDecision("left")}
            disabled={pending || !!pendingDecision}
            aria-label="Pass"
            className="flex h-14 w-14 items-center justify-center rounded-full bg-white text-rose-500 shadow-md ring-1 ring-gray-200 transition-transform hover:scale-105 active:scale-95 disabled:opacity-50 dark:bg-gray-900 dark:ring-gray-700"
          >
            <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18M6 6l12 12" /></svg>
          </button>
          <button
            type="button"
            onClick={() => requestDecision("right")}
            disabled={pending || !!pendingDecision}
            aria-label="Save"
            className="flex h-16 w-16 items-center justify-center rounded-full bg-emerald-500 text-white shadow-lg transition-transform hover:scale-105 active:scale-95 disabled:opacity-50"
          >
            <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M20 6 9 17l-5-5" /></svg>
          </button>
        </div>
      )}

      {filteredQueue && current && (
        <p className="text-xs text-gray-400 dark:text-gray-500">{filteredQueue.length} left in your queue</p>
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
