"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import RouteGuard from "@/components/RouteGuard";
import ErrorNotice from "@/components/ErrorNotice";
import PullToRefresh from "@/components/PullToRefresh";
import { STATUS_LABELS } from "@/components/StatusBadge";
import SwipeCard from "@/components/SwipeCard";
import { useAnnounce } from "@/components/LiveRegion";
import Button, { buttonClass } from "@/components/ui/Button";
import { Skeleton, SwipeCardSkeleton } from "@/components/ui/Skeleton";
import { useAuth } from "@/context/AuthContext";
import { applicationsApi, ApiError, jobsApi, profileApi } from "@/lib/api";
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
        <>
          {/* A sheet, not a popover. Anchored under the pill it opened right
              on top of the card's own title, and its five labels rode a
              slider at 9px — the smallest text in the app, on the control
              that decides which jobs you see at all. */}
          <div
            aria-hidden="true"
            onClick={() => setOpen(false)}
            className="fixed inset-0 z-40 bg-gray-900/30"
          />
          <div
            role="dialog"
            aria-label="Alcance de la búsqueda"
            className="fixed inset-x-0 bottom-0 z-50 animate-slide-up rounded-t-3xl bg-white p-5 pb-8 shadow-lift dark:bg-gray-900"
          >
            <p className="font-display text-base font-extrabold tracking-display-tight text-gray-900 dark:text-gray-50">
              ¿Qué tan lejos buscar?
            </p>
            <div className="mt-3 space-y-1.5">
              {SCOPE_LEVELS.map((lvl, index) => (
                <button
                  key={lvl.scope}
                  type="button"
                  onClick={() => {
                    onChange(index);
                    setOpen(false);
                  }}
                  aria-pressed={index === scopeIndex}
                  className={`flex min-h-[44px] w-full items-center justify-between rounded-xl px-3.5 text-sm font-semibold transition-colors ${
                    index === scopeIndex
                      ? "bg-brand-600 dark:bg-brand-200 dark:text-gray-950 text-white"
                      : "bg-gray-50 text-gray-700 hover:bg-gray-100 dark:bg-gray-800 dark:text-gray-200 dark:hover:bg-gray-700"
                  }`}
                >
                  {lvl.label}
                  {index === scopeIndex && <span aria-hidden="true">✓</span>}
                </button>
              ))}
            </div>
            {geoStatus === "denied" && geoError && (
              <p className="mt-3 text-xs text-rose-500 dark:text-rose-400">
                {geoError} Activa el permiso de ubicación en tu navegador o elige &quot;Cualquier lugar&quot;.
              </p>
            )}
            {locationText && (
              <p className="mt-3 text-xs text-gray-400 dark:text-gray-400">Tu ubicación: {locationText}</p>
            )}
          </div>
        </>
      )}
    </div>
  );
}

/** Counting words, not status labels. Reusing the labels printed "6
 * Aplicado", "0 Entrevistando", "0 Oferta" — a number followed by a
 * singular adjective, which reads as a typo rather than a count. */
const COUNT_LABELS: Record<string, string> = {
  applied: "aplicadas",
  interviewing: "entrevistas",
  offer: "ofertas",
};

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
          {counts[status]} {COUNT_LABELS[status] ?? STATUS_LABELS[status]}
        </Link>
      ))}
    </div>
  );
}

function HomeContent() {
  const { user } = useAuth();
  const router = useRouter();
  const announce = useAnnounce();
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

  // Whether the user has a career profile at all. Until they do, the match
  // engine has nothing to score against, so the queue is empty for a reason
  // that has nothing to do with having reviewed everything — see the empty
  // state below.
  const [hasProfile, setHasProfile] = useState<boolean | null>(null);

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

  // Deliberately separate from load(): a missing profile is a normal state
  // for a new account, not a failure, so it must never turn the whole page
  // into an error. 404 simply means "no profile yet".
  useEffect(() => {
    let cancelled = false;
    profileApi
      .get()
      .then(() => {
        if (!cancelled) setHasProfile(true);
      })
      .catch((err) => {
        if (cancelled) return;
        setHasProfile(err instanceof ApiError && err.status === 404 ? false : true);
      });
    return () => {
      cancelled = true;
    };
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
          : "No hay vacantes nuevas por ahora. Prueba de nuevo en un rato."
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
  // Desktop-only preview of what is behind the current card. Starts at index
  // 1 (the card under the top one) so it never repeats the card being decided.
  const upcoming = useMemo(() => (filteredQueue ?? []).slice(1, 5), [filteredQueue]);

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
        announce(
          decision === "right"
            ? `Guardado: ${target.title} en ${target.company}.`
            : `Pasaste: ${target.title} en ${target.company}. Pulsa U para deshacer.`
        );
      } catch (err) {
        const message =
          err instanceof ApiError ? err.message : "No se pudo registrar tu decisión. Intenta de nuevo.";
        setActionError(message);
        announce(message, "assertive");
      } finally {
        setPending(false);
        setPendingDecision(null);
      }
    },
    [current, pending, announce]
  );

  const handleUndoPass = useCallback(async () => {
    if (!justPassed || undoing) return;
    setUndoing(true);
    try {
      await applicationsApi.undo(justPassed.applicationId);
      setQueue((prev) => (prev ? [justPassed.job, ...prev] : [justPassed.job]));
      announce(`Deshecho. ${justPassed.job.title} vuelve a tu cola.`);
      setJustPassed(null);
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "No se pudo deshacer.";
      setActionError(message);
      announce(message, "assertive");
    } finally {
      setUndoing(false);
    }
  }, [justPassed, undoing, announce]);

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

  // Keyboard is the primary input on a desktop, where there is no thumb to
  // swipe with. The swipe stays exactly as it is — this is the same decision
  // reachable a second way, not a replacement for it.
  useEffect(() => {
    function handleKey(e: KeyboardEvent) {
      // Never decide on a card the user cannot see or is not looking at. The
      // scope sheet renders ON TOP of the card, so an arrow key pressed with
      // it open used to pass or save a job that was hidden behind the panel —
      // an invisible decision on a real posting, with only an 8-second undo.
      if (document.querySelector('[role="dialog"]')) return;

      // Typing somewhere should type, not swipe.
      const el = document.activeElement as HTMLElement | null;
      if (
        el &&
        (el.tagName === "INPUT" ||
          el.tagName === "TEXTAREA" ||
          el.tagName === "SELECT" ||
          el.isContentEditable)
      ) {
        return;
      }

      // Leave browser and OS shortcuts alone (Alt+Left is Back).
      if (e.metaKey || e.ctrlKey || e.altKey) return;

      if (e.key === "ArrowRight") {
        e.preventDefault();
        requestDecision("right");
      }
      if (e.key === "ArrowLeft") {
        e.preventDefault();
        requestDecision("left");
      }
      // Desktop conveniences: U undoes the last pass without reaching for the
      // mouse, Enter opens the card under review.
      if ((e.key === "u" || e.key === "U") && justPassed) {
        e.preventDefault();
        handleUndoPass();
      }
      if (e.key === "Enter" && current) {
        e.preventDefault();
        router.push(`/jobs/${current.id}`);
      }
    }
    window.addEventListener("keydown", handleKey);
    return () => window.removeEventListener("keydown", handleKey);
  }, [requestDecision, justPassed, handleUndoPass, current, router]);

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
            : hasProfile === false
            ? "Así funciona: subes tu CV, te buscamos vacantes y aquí decides cuáles guardar."
            : "Tu cola está al día."}
        </p>
      </div>

      {/* The scope pill gets its own line. Sharing a row with the counting
          chips, which wrap to two lines, left it vertically centered against
          them — that reads as a layout bug rather than as a control. */}
      <div className="flex w-full max-w-md">
        <ScopePill
          scopeIndex={scopeIndex}
          onChange={handleScopeChange}
          geoStatus={geoStatus}
          geoError={geoError}
          userLocation={userLocation}
        />
      </div>

      {applications && (
        <div className="-mt-1 flex w-full max-w-md">
          <StatsRow applications={applications} queueCount={filteredQueue?.length ?? 0} />
        </div>
      )}

      {pullNotice && (
        <div className="w-full max-w-md">
          <p className="text-center text-xs text-gray-400 dark:text-gray-400">{pullNotice}</p>
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

        {/* A brand-new account has an empty queue for a completely different
            reason than someone who swiped through everything, and telling
            them "Ya estás al día — revisaste todo" is simply false: they have
            reviewed nothing. Worse, the only button sent them to Buscar,
            which cannot fill the queue either — without a profile there is
            nothing for the match engine to score against. This is the one
            place the app could lose someone permanently, so it gets its own
            branch pointing at the actual next step. */}
        {!current && !hiddenByScope && hasProfile === false && (
          <EmptyState
            icon={<PinGlyph />}
            title="Empieza por tu CV"
            body="Súbelo en PDF y lo leemos por ti. Con tu perfil listo, las vacantes aparecen aquí solas, ya puntuadas."
            action={
              <Link href="/profile" className={buttonClass({ size: "sm" })}>
                Subir mi CV
              </Link>
            }
          />
        )}

        {!current && !hiddenByScope && hasProfile !== false && (
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

      {/* Desktop only (`hidden lg:block`). The swipe column is capped at
          max-w-md because that is the right width for a card you flick with a
          thumb — on a 1440px laptop that left two thirds of the screen empty.
          This fills it with the one thing the phone cannot show: what is
          coming next, so deciding has context instead of being blind. Nothing
          about the swipe changes. */}
      {upcoming.length > 0 && (
        <div className="hidden w-full max-w-md lg:block">
          <p className="mb-2 text-[11px] font-bold uppercase tracking-wide text-gray-400 dark:text-gray-500">
            A continuación
          </p>
          <ul className="space-y-1.5">
            {upcoming.map((job) => (
              <li key={job.id}>
                <Link
                  href={`/jobs/${job.id}`}
                  className="flex items-center justify-between gap-3 rounded-xl bg-white px-3 py-2 text-left shadow-soft ring-1 ring-gray-100 transition-colors hover:bg-gray-50 dark:bg-gray-900 dark:ring-gray-800 dark:hover:bg-gray-800"
                >
                  <span className="min-w-0">
                    <span className="block truncate text-[13px] font-semibold text-gray-900 dark:text-gray-100">
                      {job.title}
                    </span>
                    <span className="block truncate text-[11px] text-gray-500 dark:text-gray-400">
                      {job.company}
                      {job.location ? ` · ${job.location}` : ""}
                    </span>
                  </span>
                  {job.match?.overall_score != null && (
                    <span className="tabular shrink-0 rounded-full bg-brand-50 px-2 py-0.5 text-[11px] font-bold text-brand-700 dark:bg-brand-500/15 dark:text-brand-300">
                      {Math.round(job.match.overall_score)}
                    </span>
                  )}
                </Link>
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* Desktop only (`hidden sm:flex`). On a phone the swipe IS the
          interface and this would be noise; on a laptop there is no thumb to
          swipe with, the shortcuts already existed, and nothing ever said so.
          The swipe itself is untouched — this just makes the second way in
          discoverable. */}
      {current && (
        <div className="hidden w-full max-w-md items-center justify-center gap-4 pt-1 text-[11px] text-gray-400 sm:flex dark:text-gray-500">
          <span className="flex items-center gap-1.5">
            <Kbd>←</Kbd> Pasar
          </span>
          <span className="flex items-center gap-1.5">
            <Kbd>→</Kbd> Guardar
          </span>
          <span className="flex items-center gap-1.5">
            <Kbd>Enter</Kbd> Ver detalle
          </span>
          {justPassed && (
            <span className="flex items-center gap-1.5 text-brand-500 dark:text-brand-300">
              <Kbd>U</Kbd> Deshacer
            </span>
          )}
        </div>
      )}

      {justApplied && (
        <div className="w-full max-w-md animate-slide-up rounded-2xl bg-brand-50 p-3.5 ring-1 ring-inset ring-brand-100 dark:bg-brand-500/10 dark:ring-brand-500/20">
          <div className="flex items-start justify-between gap-2">
            <p className="text-xs leading-relaxed text-brand-900 dark:text-brand-200">
              Guardado en tu pipeline. JobPilot no lo envía por ti: para aplicar de verdad a{" "}
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

      {/* The queue count lives in the chip row at the top, which says the
          same number. Down here it landed under the fixed bottom nav, so it
          was never read — and its height is what pushed GUARDAR against the
          bar's edge. */}
      </div>
    </PullToRefresh>
  );
}

/** A keycap. Only ever rendered on `sm:` and up — see the shortcut hint row. */
function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="rounded-md border border-gray-200 bg-white px-1.5 py-0.5 font-sans text-[10px] font-bold leading-none text-gray-500 shadow-sm dark:border-gray-700 dark:bg-gray-900 dark:text-gray-400">
      {children}
    </kbd>
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
          save ? "text-emerald-600 dark:text-emerald-400" : "text-gray-400 dark:text-gray-400"
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
