"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import RouteGuard from "@/components/RouteGuard";
import Spinner from "@/components/Spinner";
import ErrorNotice from "@/components/ErrorNotice";
import PullToRefresh from "@/components/PullToRefresh";
import { STATUS_LABELS } from "@/components/StatusBadge";
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

/** A small pill trigger — tap to open the actual distance slider in a
 * popover. Used to matter as much visually as the job cards themselves;
 * this keeps it out of the way by default while staying one tap away. */
function ScopePill({
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
  const [open, setOpen] = useState(false);
  const wrapperRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    if (!open) return;
    function handleClickOutside(e: MouseEvent) {
      if (wrapperRef.current && !wrapperRef.current.contains(e.target as Node)) {
        setOpen(false);
      }
    }
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [open]);

  const locationText = userLocation
    ? [userLocation.city, userLocation.region, userLocation.country].filter(Boolean).join(", ")
    : null;

  return (
    <div ref={wrapperRef} className="relative shrink-0">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex items-center gap-1 rounded-full bg-white px-2.5 py-1 text-[11px] font-medium text-gray-600 shadow-sm ring-1 ring-gray-200 dark:bg-gray-900 dark:text-gray-300 dark:ring-gray-700"
      >
        📍 {SCOPE_LEVELS[scopeIndex].label}
        {geoStatus === "locating" && <span className="text-gray-400">…</span>}
      </button>

      {open && (
        <div className="absolute left-0 top-8 z-20 w-64 rounded-xl bg-white p-3 shadow-lg ring-1 ring-gray-100 dark:bg-gray-900 dark:ring-gray-800">
          <input
            type="range"
            min={0}
            max={SCOPE_LEVELS.length - 1}
            step={1}
            value={scopeIndex}
            onChange={(e) => onChange(Number(e.target.value))}
            className="w-full accent-brand-600"
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
      )}
    </div>
  );
}

/** Small muted chips instead of the old bordered/shadowed stat cards —
 * the counts are still all there, just no longer competing with the job
 * cards for visual weight. */
function StatsRow({ applications, queueCount }: { applications: Application[]; queueCount: number }) {
  const counts = PIPELINE_STATUSES.reduce<Record<string, number>>((acc, status) => {
    acc[status] = applications.filter((a) => a.status === status).length;
    return acc;
  }, {});

  return (
    <div className="flex min-w-0 flex-1 flex-wrap items-center gap-1.5">
      <span className="shrink-0 rounded-full bg-gray-100 px-2.5 py-1 text-[11px] font-medium text-gray-500 dark:bg-gray-800 dark:text-gray-400">
        {queueCount} en cola
      </span>
      {PIPELINE_STATUSES.map((status) => (
        <Link
          key={status}
          href={`/applications?status=${status}`}
          className="shrink-0 rounded-full bg-gray-100 px-2.5 py-1 text-[11px] font-medium text-gray-500 transition-colors hover:bg-gray-200 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700"
        >
          {counts[status]} {STATUS_LABELS[status]}
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
        // Home's stats row counts applications per status, so it needs the
        // full set, not just a page — 200 is the endpoint's max page size,
        // comfortably above what a single user racks up in practice.
        applicationsApi.list(undefined, 200, 0),
      ]);
      setQueue(matches.items);
      setApplications(apps.items);
    } catch (err) {
      setLoadError(err instanceof ApiError ? err.message : "No se pudieron cargar tus recomendaciones.");
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    load();
  }, [load]);

  const [pullNotice, setPullNotice] = useState<string | null>(null);

  const handlePullRefresh = useCallback(async () => {
    setPullNotice(null);
    try {
      const result = await jobsApi.autoImport();
      await load();
      setPullNotice(
        result.imported > 0
          ? `${result.imported} vacante${result.imported === 1 ? "" : "s"} nueva${
              result.imported === 1 ? "" : "s"
            } agregada${result.imported === 1 ? "" : "s"} a tu cola.`
          : "No hay vacantes nuevas por ahora — prueba de nuevo en un rato."
      );
    } catch (err) {
      setPullNotice(err instanceof ApiError ? err.message : "No se pudo buscar más vacantes.");
    }
  }, [load]);

  useEffect(() => {
    if (!pullNotice) return;
    const timer = setTimeout(() => setPullNotice(null), 5000);
    return () => clearTimeout(timer);
  }, [pullNotice]);

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
  const [justApplied, setJustApplied] = useState<Job | null>(null);
  const [justPassed, setJustPassed] = useState<{ job: Job; applicationId: string } | null>(null);
  const [undoing, setUndoing] = useState(false);

  const decide = useCallback(
    async (decision: "left" | "right") => {
      if (!current || pending) return;
      const target = current;
      setPending(true);
      setActionError(null);
      try {
        const application = await jobsApi.decide(target.id, { decision });
        setQueue((prev) => (prev ? prev.filter((j) => j.id !== target.id) : prev));
        setJustApplied(decision === "right" ? target : null);
        setJustPassed(decision === "left" ? { job: target, applicationId: application.id } : null);
      } catch (err) {
        setActionError(
          err instanceof ApiError ? err.message : "No se pudo registrar tu decisión. Intenta de nuevo."
        );
      } finally {
        setPending(false);
        setPendingDecision(null);
      }
    },
    [current, pending]
  );

  const handleUndoPass = useCallback(async () => {
    if (!justPassed || undoing) return;
    setUndoing(true);
    try {
      await applicationsApi.undo(justPassed.applicationId);
      setQueue((prev) => (prev ? [justPassed.job, ...prev] : [justPassed.job]));
      setJustPassed(null);
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "No se pudo deshacer.");
    } finally {
      setUndoing(false);
    }
  }, [justPassed, undoing]);

  useEffect(() => {
    if (!justPassed) return;
    const timer = setTimeout(() => setJustPassed(null), 8000);
    return () => clearTimeout(timer);
  }, [justPassed]);

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

  if (loading) return <Spinner label="Buscando tus mejores coincidencias…" />;
  if (loadError) return <ErrorNotice message={loadError} onRetry={load} />;

  const hiddenByScope = (queue?.length ?? 0) > 0 && (filteredQueue?.length ?? 0) === 0;

  return (
    <PullToRefresh onRefresh={handlePullRefresh} ignoreSelector=".swipe-drag-surface">
      <div className="flex flex-col items-center gap-3 pb-4 animate-fade-in">
      <div className="w-full max-w-md">
        <h1 className="text-xl font-bold text-gray-900 dark:text-gray-100">
          Hola{user?.full_name ? `, ${user.full_name.split(" ")[0]}` : ""} 👋
        </h1>
      </div>

      <div className="flex w-full max-w-md items-center gap-1.5">
        <ScopePill
          scopeIndex={scopeIndex}
          onChange={handleScopeChange}
          geoStatus={geoStatus}
          geoError={geoError}
          userLocation={userLocation}
        />
        {applications && <StatsRow applications={applications} queueCount={filteredQueue?.length ?? 0} />}
      </div>

      {pullNotice && (
        <div className="w-full max-w-md">
          <p className="text-center text-xs text-gray-400 dark:text-gray-500">{pullNotice}</p>
        </div>
      )}

      {actionError && (
        <div className="w-full max-w-md">
          <ErrorNotice message={actionError} />
        </div>
      )}

      {/* Scales with the viewport instead of a fixed height, so the
          decide buttons below always land within reach without needing
          to scroll first — the job cards, not the controls above, get
          the space. 66dvh (measured on-device) left the buttons landing
          exactly where the fixed bottom nav sits, ~48px of overlap;
          48dvh/420px leaves real clearance above it. */}
      <div className="relative h-[min(48dvh,420px)] w-full max-w-md">
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
            <p className="text-lg font-semibold text-gray-800 dark:text-gray-200">Ya estás al día</p>
            <p className="text-sm text-gray-500 dark:text-gray-400">
              No hay recomendaciones nuevas por ahora. Explora más vacantes en Discover para seguir.
            </p>
            <Link
              href="/discover"
              className="mt-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700"
            >
              Buscar vacantes
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
            aria-label="Pasar"
            className="flex h-14 w-14 items-center justify-center rounded-full bg-white text-rose-500 shadow-md ring-1 ring-gray-200 transition-transform hover:scale-105 active:scale-95 disabled:opacity-50 dark:bg-gray-900 dark:ring-gray-700"
          >
            <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18M6 6l12 12" /></svg>
          </button>
          <button
            type="button"
            onClick={() => requestDecision("right")}
            disabled={pending || !!pendingDecision}
            aria-label="Aplicar"
            className="flex h-16 w-16 items-center justify-center rounded-full bg-emerald-500 text-white shadow-lg transition-transform hover:scale-105 active:scale-95 disabled:opacity-50"
          >
            <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><path d="M20 6 9 17l-5-5" /></svg>
          </button>
        </div>
      )}

      {justApplied && (
        <div className="w-full max-w-md rounded-xl bg-brand-50 p-3 dark:bg-brand-900/20">
          <div className="flex items-start justify-between gap-2">
            <p className="text-xs text-brand-800 dark:text-brand-300">
              Guardado en tu pipeline. JobPilot no lo envía por ti — para aplicar de verdad a{" "}
              <strong>{justApplied.title}</strong> tienes que hacerlo en el sitio original.
            </p>
            <button
              type="button"
              onClick={() => setJustApplied(null)}
              aria-label="Cerrar"
              className="shrink-0 text-brand-400 hover:text-brand-600 dark:text-brand-500"
            >
              ✕
            </button>
          </div>
          {justApplied.source_url ? (
            <a
              href={justApplied.source_url}
              target="_blank"
              rel="noreferrer"
              className="mt-2 inline-block rounded-lg bg-brand-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-brand-700"
            >
              Aplicar en el sitio original ↗
            </a>
          ) : (
            <Link
              href={`/jobs/${justApplied.id}`}
              className="mt-2 inline-block text-xs font-semibold text-brand-700 hover:underline dark:text-brand-300"
            >
              Ver detalles del trabajo →
            </Link>
          )}
        </div>
      )}

      {justPassed && (
        <div className="w-full max-w-md rounded-xl bg-gray-100 p-3 dark:bg-gray-800">
          <div className="flex items-center justify-between gap-2">
            <p className="text-xs text-gray-600 dark:text-gray-400">
              Pasaste <strong>{justPassed.job.title}</strong>.
            </p>
            <button
              type="button"
              onClick={handleUndoPass}
              disabled={undoing}
              className="shrink-0 rounded-lg bg-white px-3 py-1.5 text-xs font-semibold text-gray-700 shadow-sm ring-1 ring-gray-200 hover:bg-gray-50 disabled:opacity-60 dark:bg-gray-900 dark:text-gray-200 dark:ring-gray-700"
            >
              {undoing ? "Deshaciendo…" : "Deshacer"}
            </button>
          </div>
        </div>
      )}

      {filteredQueue && current && (
        <p className="text-xs text-gray-400 dark:text-gray-500">Quedan {filteredQueue.length} en tu cola</p>
      )}
      </div>
    </PullToRefresh>
  );
}

export default function HomePage() {
  return (
    <RouteGuard>
      <HomeContent />
    </RouteGuard>
  );
}
