"use client";

import Link from "next/link";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import RouteGuard from "@/components/RouteGuard";
import ErrorNotice from "@/components/ErrorNotice";
import PullToRefresh from "@/components/PullToRefresh";
import { STATUS_LABELS } from "@/components/StatusBadge";
import SwipeCard from "@/components/SwipeCard";
import Button, { buttonClass } from "@/components/ui/Button";
import { Skeleton, SwipeCardSkeleton } from "@/components/ui/Skeleton";
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
        aria-expanded={open}
        className="flex min-h-[30px] items-center gap-1 rounded-full bg-white px-2.5 text-[11px] font-semibold text-gray-600 shadow-soft ring-1 ring-gray-200 transition-colors hover:bg-gray-50 active:scale-95 dark:bg-gray-900 dark:text-gray-300 dark:ring-gray-700 dark:hover:bg-gray-800"
      >
        <svg width="11" height="11" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round" strokeLinejoin="round" className="shrink-0 text-brand-500">
          <path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z" />
          <circle cx="12" cy="10" r="3" />
        </svg>
        {SCOPE_LEVELS[scopeIndex].label}
        {geoStatus === "locating" && <span className="text-gray-400">…</span>}
      </button>

      {open && (
        <div className="absolute left-0 top-9 z-20 w-64 animate-scale-in rounded-2xl bg-white p-3.5 shadow-lift ring-1 ring-gray-200 dark:bg-gray-900 dark:ring-gray-800">
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
      <span className="tabular flex min-h-[30px] shrink-0 items-center rounded-full bg-gray-100 px-2.5 text-[11px] font-semibold text-gray-500 dark:bg-gray-800 dark:text-gray-400">
        {queueCount} en cola
      </span>
      {PIPELINE_STATUSES.map((status) => (
        <Link
          key={status}
          href={`/applications?status=${status}`}
          className="tabular flex min-h-[30px] shrink-0 items-center rounded-full bg-gray-100 px-2.5 text-[11px] font-semibold text-gray-500 transition-colors hover:bg-gray-200 hover:text-gray-700 active:scale-95 dark:bg-gray-800 dark:text-gray-400 dark:hover:bg-gray-700 dark:hover:text-gray-200"
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

  if (loading) return <HomeSkeleton />;
  if (loadError) return <ErrorNotice message={loadError} onRetry={load} />;

  const hiddenByScope = (queue?.length ?? 0) > 0 && (filteredQueue?.length ?? 0) === 0;

  return (
    <PullToRefresh onRefresh={handlePullRefresh} ignoreSelector=".swipe-drag-surface">
      <div className="flex flex-col items-center gap-3 pb-4 animate-fade-in">
      <div className="w-full max-w-md">
        <h1 className="font-display text-[22px] font-extrabold leading-tight tracking-display-tight text-gray-900 dark:text-gray-50">
          Hola{user?.full_name ? `, ${user.full_name.split(" ")[0]}` : ""}
        </h1>
        <p className="mt-0.5 text-[13px] text-gray-500 dark:text-gray-400">
          {current
            ? "Desliza a la derecha para guardar, a la izquierda para pasar."
            : "Tu cola está al día."}
        </p>
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
          <EmptyState
            icon={<PinGlyph />}
            title="Nada en este alcance"
            body={`Hay recomendaciones esperando, pero ninguna coincide con "${SCOPE_LEVELS[scopeIndex].label}". Prueba un alcance más amplio.`}
            action={
              <Button size="sm" onClick={() => setScopeIndex(DEFAULT_SCOPE_INDEX)}>
                Ver cualquier lugar
              </Button>
            }
          />
        )}

        {!current && !hiddenByScope && (
          <EmptyState
            icon={<CheckGlyph />}
            title="Ya estás al día"
            body="Revisaste todo lo que teníamos para ti. Desliza hacia abajo para buscar nuevas, o explora por tu cuenta."
            action={
              <Link href="/discover" className={buttonClass({ size: "sm" })}>
                Buscar vacantes
              </Link>
            }
          />
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
        <div className="flex items-center gap-5">
          {/* Labelled, not just iconographic. "✕ / ✓" alone reads as
              delete/confirm; here the left action is a soft "pass" that's
              undoable and the right one only saves to the pipeline (it
              never submits an application), so the words carry meaning the
              icons can't. */}
          <DecisionButton
            onClick={() => requestDecision("left")}
            disabled={pending || !!pendingDecision}
            label="Pasar"
            tone="pass"
          />
          <DecisionButton
            onClick={() => requestDecision("right")}
            disabled={pending || !!pendingDecision}
            label="Guardar"
            tone="save"
          />
        </div>
      )}

      {justApplied && (
        <div className="w-full max-w-md animate-slide-up rounded-2xl bg-brand-50 p-3.5 ring-1 ring-inset ring-brand-100 dark:bg-brand-500/10 dark:ring-brand-500/20">
          <div className="flex items-start justify-between gap-2">
            <p className="text-xs leading-relaxed text-brand-900 dark:text-brand-200">
              Guardado en tu pipeline. JobPilot no lo envía por ti — para aplicar de verdad a{" "}
              <strong className="font-bold">{justApplied.title}</strong> tienes que hacerlo en el sitio
              original.
            </p>
            <button
              type="button"
              onClick={() => setJustApplied(null)}
              aria-label="Cerrar"
              className="-mr-1 -mt-1 flex h-7 w-7 shrink-0 items-center justify-center rounded-lg text-brand-400 transition-colors hover:bg-brand-100 hover:text-brand-700 dark:hover:bg-brand-500/20"
            >
              <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round"><path d="M18 6 6 18M6 6l12 12" /></svg>
            </button>
          </div>
          {justApplied.source_url ? (
            <a
              href={justApplied.source_url}
              target="_blank"
              rel="noreferrer"
              className={buttonClass({ size: "sm", className: "mt-2.5" })}
            >
              Aplicar en el sitio original ↗
            </a>
          ) : (
            <Link
              href={`/jobs/${justApplied.id}`}
              className={buttonClass({ variant: "secondary", size: "sm", className: "mt-2.5" })}
            >
              Ver detalles del trabajo →
            </Link>
          )}
        </div>
      )}

      {justPassed && (
        <div className="flex w-full max-w-md animate-slide-up items-center justify-between gap-2 rounded-2xl bg-gray-900 p-2 pl-4 dark:bg-gray-800">
          <p className="min-w-0 truncate text-xs text-gray-300">
            Pasaste <strong className="font-semibold text-white">{justPassed.job.title}</strong>
          </p>
          <Button
            variant="secondary"
            size="sm"
            onClick={handleUndoPass}
            loading={undoing}
            className="shrink-0"
          >
            {undoing ? "Deshaciendo…" : "Deshacer"}
          </Button>
        </div>
      )}

      {filteredQueue && current && (
        <p className="tabular text-[11px] font-medium text-gray-400 dark:text-gray-500">
          Quedan {filteredQueue.length} en tu cola
        </p>
      )}
      </div>
    </PullToRefresh>
  );
}

/** The two swipe actions. Sized well above the 44px tap-target floor (the
 * old buttons were 56/64px circles with no label), and colored by outcome
 * rather than both being neutral chrome. */
function DecisionButton({
  onClick,
  disabled,
  label,
  tone,
}: {
  onClick: () => void;
  disabled: boolean;
  label: string;
  tone: "pass" | "save";
}) {
  const save = tone === "save";
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      aria-label={label}
      className={`group flex flex-col items-center gap-1.5 transition-transform active:scale-95 disabled:opacity-40 ${
        disabled ? "" : "hover:-translate-y-0.5"
      }`}
    >
      <span
        className={`flex items-center justify-center rounded-full transition-shadow ${
          save
            ? "h-[64px] w-[64px] bg-emerald-500 text-white shadow-[0_8px_24px_-6px_rgb(16_185_129_/_0.6)] group-hover:shadow-[0_12px_30px_-6px_rgb(16_185_129_/_0.7)]"
            : "h-14 w-14 bg-white text-rose-500 shadow-card ring-1 ring-gray-200 dark:bg-gray-900 dark:ring-gray-700"
        }`}
      >
        {save ? (
          <svg width="30" height="30" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round"><path d="M20 6 9 17l-5-5" /></svg>
        ) : (
          <svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.6" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18M6 6l12 12" /></svg>
        )}
      </span>
      <span
        className={`text-[11px] font-bold uppercase tracking-wide ${
          save ? "text-emerald-600 dark:text-emerald-400" : "text-gray-400 dark:text-gray-500"
        }`}
      >
        {label}
      </span>
    </button>
  );
}

/** Shared shell for Home's two "nothing to show" states, so they can't
 * drift apart the way the two hand-written copies did. */
function EmptyState({
  icon,
  title,
  body,
  action,
}: {
  icon: React.ReactNode;
  title: string;
  body: string;
  action: React.ReactNode;
}) {
  return (
    <div className="flex h-full flex-col items-center justify-center gap-3 rounded-3xl bg-white/60 p-8 text-center ring-1 ring-inset ring-gray-200 dark:bg-gray-900/40 dark:ring-gray-800">
      <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-brand-50 text-brand-600 dark:bg-brand-500/15 dark:text-brand-400">
        {icon}
      </span>
      <p className="font-display text-lg font-extrabold tracking-display-tight text-gray-900 dark:text-gray-100">
        {title}
      </p>
      <p className="max-w-[36ch] text-sm leading-relaxed text-gray-500 dark:text-gray-400">{body}</p>
      <div className="mt-1">{action}</div>
    </div>
  );
}

function PinGlyph() {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M20 10c0 6-8 12-8 12s-8-6-8-12a8 8 0 0 1 16 0Z" />
      <circle cx="12" cy="10" r="3" />
    </svg>
  );
}

function CheckGlyph() {
  return (
    <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
      <path d="M21.8 10.7V12a10 10 0 1 1-5.9-9.1" />
      <path d="m9 11 3 3L22 4" />
    </svg>
  );
}

/** Mirrors the real Home layout (greeting, filter row, card, buttons) so
 * the screen doesn't visibly re-assemble itself when the queue lands. */
function HomeSkeleton() {
  return (
    <div className="flex flex-col items-center gap-3 pb-4">
      <div className="w-full max-w-md space-y-2">
        <Skeleton className="h-6 w-40" />
        <Skeleton className="h-3 w-64" />
      </div>
      <div className="flex w-full max-w-md gap-1.5">
        <Skeleton className="h-7 w-24 rounded-full" />
        <Skeleton className="h-7 w-20 rounded-full" />
        <Skeleton className="h-7 w-20 rounded-full" />
      </div>
      <div className="h-[min(48dvh,420px)] w-full max-w-md">
        <SwipeCardSkeleton />
      </div>
      <div className="flex items-center gap-5">
        <Skeleton className="h-14 w-14 rounded-full" />
        <Skeleton className="h-16 w-16 rounded-full" />
      </div>
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
