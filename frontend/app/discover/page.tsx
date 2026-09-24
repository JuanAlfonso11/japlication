"use client";

import WorkAuthBadge from "@/components/WorkAuthBadge";
import { useEffect, useMemo, useState } from "react";
import RouteGuard from "@/components/RouteGuard";
import ErrorNotice from "@/components/ErrorNotice";
import ImportedJobCard from "@/components/ImportedJobCard";
import SkillTag from "@/components/SkillTag";
import { inputClass, Select } from "@/components/ui/Field";
import Button from "@/components/ui/Button";
import PageHeader from "@/components/ui/PageHeader";
import { ListSkeleton } from "@/components/ui/Skeleton";
import { useAnnounce } from "@/components/LiveRegion";
import Link from "next/link";
import { buttonClass } from "@/components/ui/Button";
import { ApiError, jobsApi, profileApi } from "@/lib/api";
import { EXTERNAL_PLATFORM_GROUPS } from "@/lib/externalPlatforms";
import { importAndMatch, type AddedJob } from "@/lib/jobActions";
import {
  EXPERIENCE_LEVEL_LABELS,
  JOB_TITLE_GROUPS,
  LOCATION_OPTIONS,
  PROVIDER_LABELS,
  REMOTE_TYPE_LABELS,
  type AggregateSourceStatus,
  type ExperienceLevel,
  type ExternalJobResult,
  type ExternalProvider,
  type RemoteType,
} from "@/lib/types";

const EXPERIENCE_LEVELS: ExperienceLevel[] = ["internship", "entry", "mid", "senior", "lead"];
const REMOTE_TYPES: RemoteType[] = ["remote", "hybrid", "onsite"];
// Sentinel for the "type your own title" option. A value no real job title
// can collide with, so it is never mistaken for a search term.
const CUSTOM_TITLE_VALUE = "__custom__";

function SourceBadge({ source }: { source: ExternalProvider }) {
  return (
    <span className="inline-flex items-center rounded-full bg-gray-100 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-gray-500 dark:bg-gray-800 dark:text-gray-400">
      {PROVIDER_LABELS[source] ?? source}
    </span>
  );
}

function LevelBadge({ level }: { level: string }) {
  const label = EXPERIENCE_LEVEL_LABELS[level as ExperienceLevel] ?? level;
  return (
    <span className="inline-flex items-center rounded-full bg-brand-50 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-brand-700 dark:bg-brand-900/30 dark:text-brand-300">
      {label}
    </span>
  );
}

function ExternalResultCard({
  result,
  onImport,
}: {
  result: ExternalJobResult;
  onImport: (result: ExternalJobResult) => Promise<AddedJob>;
}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [added, setAdded] = useState<AddedJob | null>(null);
  const imported = added !== null;

  async function handleImport() {
    setLoading(true);
    setError(null);
    try {
      setAdded(await onImport(result));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo agregar este trabajo.");
    } finally {
      setLoading(false);
    }
  }

  const budget =
    result.salary_min != null
      ? `${result.salary_currency ?? ""} ${result.salary_min.toLocaleString()}${
          result.salary_max && result.salary_max !== result.salary_min
            ? `–${result.salary_max.toLocaleString()}`
            : ""
        }`.trim()
      : null;

  return (
    <div className="rounded-2xl bg-white p-4 shadow-soft ring-1 ring-gray-100 transition-shadow hover:shadow-card dark:bg-gray-900 dark:ring-gray-800">
      <div className="flex items-start justify-between gap-3">
        <div className="min-w-0 flex-1">
          <div className="mb-1.5 flex flex-wrap items-center gap-1.5">
            <SourceBadge source={result.source} />
            {result.seniority && <LevelBadge level={result.seniority} />}
            <WorkAuthBadge workAuth={result.work_auth} />
          </div>
          <h3 className="font-display font-bold leading-snug text-gray-900 dark:text-gray-100">
            {result.title}
          </h3>
          <p className="mt-0.5 text-[13px] text-gray-500 dark:text-gray-400">
            <span className="font-semibold text-gray-700 dark:text-gray-300">{result.company}</span>
            {result.location ? ` · ${result.location}` : ""}
          </p>
          {(budget || result.posted_at_text) && (
            <p className="mt-1 text-[11px] font-medium text-gray-400 dark:text-gray-400">
              {budget && <span className="text-emerald-600 dark:text-emerald-400">{budget}</span>}
              {budget && result.posted_at_text ? " · " : ""}
              {result.posted_at_text}
            </p>
          )}
        </div>
        {/* Secondary, always: a results page is a list to read, and a column
            of primary buttons down the side of it competes with every job
            title for attention. */}
        <Button
          size="sm"
          variant="secondary"
          onClick={handleImport}
          disabled={imported}
          loading={loading}
          className="shrink-0"
        >
          {imported ? "Agregado ✓" : loading ? "Agregando…" : "Agregar"}
        </Button>
      </div>
      {result.skills_required?.length > 0 && (
        <div className="mt-2.5 flex flex-wrap gap-1.5">
          {result.skills_required.slice(0, 8).map((s) => (
            <SkillTag key={s.name} label={s.name} />
          ))}
        </div>
      )}
      {error && <p className="mt-2 text-xs font-medium text-rose-600 dark:text-rose-400">{error}</p>}
      {added && <ImportedJobCard job={added} compact />}
    </div>
  );
}

// A keyed provider (Adzuna/USAJobs/SerpApi) without its key
// in .env always fails with this exact message (see each service's
// is_configured() check) — that's expected, not broken, so it gets a
// neutral "sin clave" badge instead of the alarming red "error" one a
// genuine network/parsing failure gets.
function isNotConfigured(error: string): boolean {
  return error.includes("is not configured");
}

// Una fuente que no respondió dentro del plazo de la búsqueda sigue cargando
// en segundo plano y responde con este aviso en vez de con vacantes
// (_STILL_LOADING en backend/app/api/v1/routers/jobs.py). No es una falla: la
// próxima búsqueda ya la trae, por eso lleva un chip neutro.
function isPending(error: string): boolean {
  return error.includes("segundo plano");
}

/** Cuánto aportó cada fuente, y el total.
 *
 * Antes esto era solo una fila de chips, uno por proveedor. Con 15 fuentes
 * eso son 15 chips sin jerarquía, y —más importante— faltaba el número que
 * en realidad se quiere de un vistazo: cuántas vacantes trajo la búsqueda
 * en total.
 *
 * El detalle de la resta importa: los conteos por fuente son ANTES de
 * deduplicar (a propósito: reportan lo que devolvió cada proveedor, que es
 * lo que sirve para notar que una se quedó muda), mientras que la lista de
 * abajo ya está deduplicada. Sin decirlo, la suma de los chips no cuadra
 * con lo que se ve y parece un error de la app. Por eso las duplicadas
 * ocultas se muestran explícitamente.
 */
function SourcesSummary({
  sources,
  shownCount,
}: {
  sources: AggregateSourceStatus[];
  /** Resultados realmente devueltos, ya deduplicados. */
  shownCount: number;
}) {
  const [open, setOpen] = useState(false);

  const failed = sources.filter((s) => s.error && !isNotConfigured(s.error) && !isPending(s.error));
  const unconfigured = sources.filter((s) => s.error && isNotConfigured(s.error));
  const pending = sources.filter((s) => s.error && isPending(s.error));
  const answered = sources.filter((s) => !s.error);
  const rawTotal = answered.reduce((sum, s) => sum + s.count, 0);
  const duplicates = Math.max(0, rawTotal - shownCount);

  // Las que más aportaron primero: con 15 fuentes, el orden alfabético
  // esconde justamente lo que se quiere ver.
  const ordered = [...sources].sort((a, b) => {
    if (Boolean(a.error) !== Boolean(b.error)) return a.error ? 1 : -1;
    return b.count - a.count;
  });

  return (
    <div className="space-y-2">
      <div className="flex flex-wrap items-center gap-1.5 text-xs">
        <span className="tabular rounded-full bg-brand-50 px-2.5 py-1 font-bold text-brand-700 dark:bg-brand-500/15 dark:text-brand-300">
          {shownCount} vacante{shownCount === 1 ? "" : "s"}
        </span>
        <span className="tabular rounded-full bg-gray-100 px-2.5 py-1 font-semibold text-gray-600 dark:bg-gray-800 dark:text-gray-300">
          {answered.length} de {sources.length} fuentes
        </span>
        {duplicates > 0 && (
          <span
            className="tabular rounded-full bg-gray-100 px-2.5 py-1 font-medium text-gray-500 dark:bg-gray-800 dark:text-gray-400"
            title="La misma vacante publicada en varias fuentes, o repetida por ciudad, se muestra una sola vez."
          >
            {duplicates} duplicada{duplicates === 1 ? "" : "s"} oculta{duplicates === 1 ? "" : "s"}
          </span>
        )}
        {failed.length > 0 && (
          <span className="rounded-full bg-rose-50 px-2.5 py-1 font-semibold text-rose-600 dark:bg-rose-500/15 dark:text-rose-400">
            {failed.length} sin responder
          </span>
        )}
        {/* "buscando…" was a promise the app never kept: these providers
            missed the 12s deadline, their results land in the server-side
            cache, and nothing here ever picks them up — you had to press
            Buscar again. Saying so is the honest version, and it tells the
            user the one action that actually works. */}
        {pending.length > 0 && (
          <span
            className="rounded-full bg-gray-100 px-2.5 py-1 font-semibold text-gray-600 dark:bg-gray-800 dark:text-gray-300"
            title={pending[0].error ?? undefined}
          >
            {pending.map((s) => PROVIDER_LABELS[s.provider] ?? s.provider).join(", ")} tardaron —
            busca otra vez en un momento para incluirlas
          </span>
        )}
        <button
          type="button"
          onClick={() => setOpen((v) => !v)}
          aria-expanded={open}
          className="rounded-full px-2 py-1 font-bold text-brand-600 transition-colors hover:text-brand-700 dark:text-brand-400 dark:hover:text-brand-300"
        >
          {open ? "Ocultar detalle" : "Ver por fuente"}
        </button>
      </div>

      {open && (
        <div className="flex flex-wrap items-center gap-1.5 text-xs text-gray-400 dark:text-gray-400">
          {ordered.map((s) => {
            const notConfigured = s.error ? isNotConfigured(s.error) : false;
            const searching = s.error ? isPending(s.error) : false;
            return (
              <span
                key={s.provider}
                className={`tabular rounded-full px-2 py-0.5 ${
                  s.error && !notConfigured && !searching
                    ? "bg-rose-50 text-rose-600 dark:bg-rose-500/15 dark:text-rose-400"
                    : s.count > 0
                    ? "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300"
                    : "bg-gray-50 text-gray-400 dark:bg-gray-800/60 dark:text-gray-400"
                }`}
                title={s.error ?? undefined}
              >
                {PROVIDER_LABELS[s.provider] ?? s.provider}:{" "}
                {notConfigured ? "sin clave" : searching ? "buscando…" : s.error ? "error" : s.count}
              </span>
            );
          })}
        </div>
      )}

      {failed.length > 0 && (
        // Grey, not alarm-red, and with the verb agreeing: "2 fuentes no
        // respondió" in red read as a broken search when the rest of the
        // results are complete.
        <p className="text-xs text-gray-500 dark:text-gray-400">
          {failed.length === 1 ? "1 fuente no respondió" : `${failed.length} fuentes no respondieron`}. El
          resto de resultados sigue completo.
        </p>
      )}
      {failed.length === 0 && unconfigured.length > 0 && (
        <p className="text-xs text-gray-400 dark:text-gray-400">
          {unconfigured.length === 1
            ? "1 fuente sin clave configurada"
            : `${unconfigured.length} fuentes sin clave configurada`}
          . El resto está completo.
        </p>
      )}
    </div>
  );
}

function ExternalPlatformsSection() {
  const [open, setOpen] = useState(false);
  return (
    <div className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-gray-100 dark:bg-gray-900 dark:ring-gray-800">
      <button
        type="button"
        onClick={() => setOpen((v) => !v)}
        className="flex w-full items-center justify-between text-left"
      >
        <div>
          <h2 className="font-semibold text-gray-900 dark:text-gray-100">Otras plataformas para buscar</h2>
          <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">
            No tienen API pública, así que no aparecen en la búsqueda de arriba, pero son buenas opciones
            para revisar y aplicar manualmente desde RD.
          </p>
        </div>
        <span className="shrink-0 text-gray-400 dark:text-gray-400">{open ? "−" : "+"}</span>
      </button>
      {open && (
        <div className="mt-4 space-y-4">
          {EXTERNAL_PLATFORM_GROUPS.map((group) => (
            <div key={group.label}>
              <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-400">
                {group.label}
              </h3>
              <div className="flex flex-wrap gap-2">
                {group.platforms.map((p) => (
                  <a
                    key={p.name}
                    href={p.url}
                    target="_blank"
                    rel="noopener noreferrer"
                    title={p.note}
                    className="rounded-lg border border-gray-100 bg-gray-50 px-3 py-1.5 text-xs font-medium text-gray-700 hover:border-brand-200 hover:bg-brand-50 hover:text-brand-700 dark:border-gray-800 dark:bg-gray-800/60 dark:text-gray-300 dark:hover:bg-brand-900/30 dark:hover:text-brand-300"
                  >
                    {p.name} ↗
                  </a>
                ))}
              </div>
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

const RESULTS_PAGE = 20;

/** The results list, a page at a time.
 *
 * A search returned 741 cards and painted all of them at once: the 44 seconds
 * measured from tapping "Buscar" to seeing results are mostly this, not the
 * network — the client gives up on a request at 20s and never retried.
 * The visible count lives in here so a new search remounts it (the parent
 * keys it by the search) and the list starts from the top again. */
function ResultsList({
  results,
  onImport,
}: {
  results: ExternalJobResult[];
  onImport: (result: ExternalJobResult) => Promise<AddedJob>;
}) {
  const [visible, setVisible] = useState(RESULTS_PAGE);
  const shown = results.slice(0, visible);

  return (
    <div className="space-y-3">
      {shown.map((r) => (
        <ExternalResultCard key={`${r.source}:${r.external_id}`} result={r} onImport={onImport} />
      ))}
      {visible < results.length && (
        <button
          type="button"
          onClick={() => setVisible((v) => v + RESULTS_PAGE)}
          className="w-full rounded-xl bg-white px-4 py-3 text-sm font-semibold text-gray-700 shadow-soft ring-1 ring-inset ring-gray-200 transition-colors hover:bg-gray-50 dark:bg-gray-900 dark:text-gray-200 dark:ring-gray-700 dark:hover:bg-gray-800"
        >
          Ver {Math.min(RESULTS_PAGE, results.length - visible)} más de {results.length}
        </button>
      )}
    </div>
  );
}

/** What you searched for last time, not what it found.
 *
 * This screen opened blank every time, so coming back meant setting the same
 * four filters again. The results themselves deliberately aren't stored:
 * hundreds of postings is a lot to keep around, and a job list goes stale
 * while a set of filters doesn't. */
const FILTERS_KEY = "jobpilot.discover.filters";

type StoredFilters = {
  q: string;
  location: string;
  remoteType: string;
  level: string;
  minSalary: string;
};

function readStoredFilters(): Partial<StoredFilters> {
  try {
    const raw = window.sessionStorage.getItem(FILTERS_KEY);
    return raw ? (JSON.parse(raw) as Partial<StoredFilters>) : {};
  } catch {
    // Private mode, blocked storage, or something that isn't JSON any more.
    return {};
  }
}

function DiscoverContent() {
  const announce = useAnnounce();
  const [q, setQ] = useState("");
  // True when the user chose "Otro…" and is typing a title the list does not
  // have. Restored below if a remembered filter is not one of the presets.
  const [customTitle, setCustomTitle] = useState(false);
  // Titles from the user's own CV, shown first and preselected so a doctor's
  // search defaults to medicine and an engineer's to engineering.
  const [cvTitles, setCvTitles] = useState<string[]>([]);
  const [location, setLocation] = useState("");
  const [remoteType, setRemoteType] = useState<RemoteType | "">("remote");
  const [experienceLevelFilter, setExperienceLevelFilter] = useState<ExperienceLevel | "">("");
  const [minSalary, setMinSalary] = useState("");
  const [results, setResults] = useState<ExternalJobResult[]>([]);
  const [sources, setSources] = useState<AggregateSourceStatus[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [searched, setSearched] = useState(false);
  // null until known. Without a profile, what gets added cannot be scored,
  // so it goes to the Pipeline — said up front, not discovered afterwards.
  const [hasProfile, setHasProfile] = useState<boolean | null>(null);

  // On mount, not while building the state: reading storage during the first
  // render makes the server's HTML and the client's disagree, and React
  // complains about exactly that.
  useEffect(() => {
    const stored = readStoredFilters();
    if (stored.q) {
      setQ(stored.q);
      // A remembered title that is not one of the presets was typed by hand,
      // so restore the text field rather than a select that cannot show it.
      const isPreset = JOB_TITLE_GROUPS.some((g) => g.options.includes(stored.q as string));
      if (!isPreset) setCustomTitle(true);
    }
    if (stored.location) setLocation(stored.location);
    // The two typed ones are checked against their own lists, so a value
    // left over from an older build can't strand a select on an option that
    // no longer exists.
    if (stored.remoteType && REMOTE_TYPES.includes(stored.remoteType as RemoteType)) {
      setRemoteType(stored.remoteType as RemoteType);
    }
    if (stored.level && EXPERIENCE_LEVELS.includes(stored.level as ExperienceLevel)) {
      setExperienceLevelFilter(stored.level as ExperienceLevel);
    }
    if (stored.minSalary) setMinSalary(stored.minSalary);

    profileApi
      .get()
      .then(() => setHasProfile(true))
      .catch((err) => setHasProfile(!(err instanceof ApiError && err.status === 404)));

    jobsApi
      .searchSuggestions()
      .then((titles) => {
        setCvTitles(titles);
        if (!stored.q && titles[0]) setQ(titles[0]);
        if (stored.q && titles.includes(stored.q)) setCustomTitle(false);
      })
      .catch(() => {
        // No suggestions just means the plain list; the backend still falls
        // back to the CV title when the search goes out empty.
      });
  }, []);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    // An empty title searched for "anything": 1034 random postings, the first
    // a recruiter job, for a mechanical engineer with no CV uploaded yet.
    if (!q.trim()) {
      setError("Elige un puesto de la lista, o escribe el tuyo con «Otro… (escribir)».");
      return;
    }
    setLoading(true);
    setError(null);
    // Clear the previous run's results and source chips. Leaving them on
    // screen while the next search ran meant the page looked identical for
    // the ~40 seconds a 15-source fan-out takes (measured: 44s tap to
    // results, against a client that gives up at 20s) — the only thing that
    // changed was the button label, so it read as "the button did nothing"
    // and invited a second tap or a reload.
    setResults([]);
    setSources([]);
    announce("Buscando en todas las fuentes. Esto puede tardar hasta un minuto.");
    try {
      window.sessionStorage.setItem(
        FILTERS_KEY,
        JSON.stringify({
          q,
          location,
          remoteType,
          level: experienceLevelFilter,
          minSalary,
        } satisfies StoredFilters)
      );
    } catch {
      // Not being able to remember the filters is not a reason to not search.
    }
    try {
      const data = await jobsApi.searchAggregate({
        q: q || undefined,
        location: location || undefined,
        remote_type: remoteType || undefined,
        experience_level: experienceLevelFilter || undefined,
      });
      setResults(data.results);
      setSources(data.sources);
      setSearched(true);
      const answered = data.sources.filter((s) => !s.error).length;
      announce(
        data.results.length === 0
          ? "La búsqueda terminó sin resultados."
          : `${data.results.length} vacantes encontradas en ${answered} de ${data.sources.length} fuentes.`
      );
    } catch (err) {
      const message = err instanceof ApiError ? err.message : "Falló la búsqueda.";
      setError(message);
      announce(message, "assertive");
    } finally {
      setLoading(false);
    }
  }

  const minSalaryValue = minSalary ? Number(minSalary) : null;
  const filteredResults = useMemo(() => {
    if (!minSalaryValue) return results;
    return results.filter((r) => {
      const best = r.salary_max ?? r.salary_min;
      return best != null && best >= minSalaryValue;
    });
  }, [results, minSalaryValue]);

  async function handleImport(result: ExternalJobResult): Promise<AddedJob> {
    const job = await jobsApi.importExternal({ source: result.source, external_id: result.external_id });
    return importAndMatch(job);
  }

  return (
    <div className="space-y-6 pb-4 animate-fade-in">
      <PageHeader
        title="Buscar trabajos"
        subtitle="Busca en todas las fuentes a la vez, LinkedIn incluido, sin repetidos. Lo que agregues aparece en Inicio con su puntaje de match."
      />

      {hasProfile === false && (
        <div className="rounded-2xl bg-amber-50 p-4 ring-1 ring-inset ring-amber-200 dark:bg-amber-500/10 dark:ring-amber-500/30">
          <p className="text-sm font-semibold text-amber-900 dark:text-amber-200">Todavía no subiste tu CV</p>
          <p className="mt-1 text-xs leading-relaxed text-amber-800 dark:text-amber-300">
            Puedes buscar y agregar vacantes: se guardan en tu Pipeline. Pero sin tu CV no sabemos qué
            tanto encajan ni qué buscarte. Súbelo primero y el resto se hace solo.
          </p>
          <Link href="/profile" className={buttonClass({ size: "sm", className: "mt-2.5" })}>
            Subir mi CV
          </Link>
        </div>
      )}

      <div className="rounded-2xl bg-white p-5 shadow-soft ring-1 ring-gray-100 dark:bg-gray-900 dark:ring-gray-800">
        <div className="space-y-4">
          <form onSubmit={handleSubmit} className="space-y-2">
            <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap">
              {/* The dropdown is the fast path — it keeps the common titles
                  one tap away and avoids the useless free-text searches it
                  was designed to prevent. But being closed meant a title that
                  is not on the list ("Site Reliability Engineer", "Analista
                  de datos junior") simply could not be searched at all, which
                  turns the search box into a catalogue. "Otro…" opens a text
                  field; everything else is unchanged. */}
              {customTitle ? (
                <div className="col-span-2 flex gap-2 sm:min-w-[180px] sm:flex-1">
                  <input
                    type="text"
                    autoFocus
                    value={q}
                    onChange={(e) => setQ(e.target.value)}
                    placeholder="Escribe el puesto"
                    aria-label="Puesto"
                    className={inputClass}
                  />
                  <button
                    type="button"
                    onClick={() => {
                      setCustomTitle(false);
                      setQ("");
                    }}
                    className="shrink-0 rounded-lg px-2 text-xs font-semibold text-gray-500 underline decoration-dotted underline-offset-2 hover:text-gray-700 dark:text-gray-400 dark:hover:text-gray-200"
                  >
                    Lista
                  </button>
                </div>
              ) : (
                <Select
                  value={q}
                  onChange={(e) => {
                    if (e.target.value === CUSTOM_TITLE_VALUE) {
                      setCustomTitle(true);
                      setQ("");
                      return;
                    }
                    setQ(e.target.value);
                  }}
                  className="col-span-2 sm:min-w-[180px] sm:flex-1"
                >
                  <option value="">{cvTitles.length ? "Puesto (según tu CV)" : "Puesto"}</option>
                  {cvTitles.length > 0 && (
                    <optgroup label="Según tu CV">
                      {cvTitles.map((title) => (
                        <option key={title} value={title}>
                          {title}
                        </option>
                      ))}
                    </optgroup>
                  )}
                  {JOB_TITLE_GROUPS.map((group) => (
                    <optgroup key={group.label} label={group.label}>
                      {group.options.map((title) => (
                        <option key={title} value={title}>
                          {title}
                        </option>
                      ))}
                    </optgroup>
                  ))}
                  <option value={CUSTOM_TITLE_VALUE}>Otro… (escribir)</option>
                </Select>
              )}
              <Select
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                className="sm:min-w-[160px] sm:flex-1"
              >
                <option value="">Ubicación</option>
                {LOCATION_OPTIONS.map((loc) => (
                  <option key={loc} value={loc}>
                    {loc}
                  </option>
                ))}
              </Select>
              <Select
                value={remoteType}
                onChange={(e) => setRemoteType(e.target.value as RemoteType | "")}
                className="sm:min-w-[160px] sm:flex-1"
              >
                <option value="">Modalidad</option>
                {REMOTE_TYPES.map((rt) => (
                  <option key={rt} value={rt}>
                    {REMOTE_TYPE_LABELS[rt]}
                  </option>
                ))}
              </Select>
              <Select
                value={experienceLevelFilter}
                onChange={(e) => setExperienceLevelFilter(e.target.value as ExperienceLevel | "")}
                className="sm:min-w-[160px] sm:flex-1"
              >
                <option value="">Nivel</option>
                {EXPERIENCE_LEVELS.map((lvl) => (
                  <option key={lvl} value={lvl}>
                    {EXPERIENCE_LEVEL_LABELS[lvl]}
                  </option>
                ))}
              </Select>
              <input
                type="number"
                min={0}
                step={1000}
                inputMode="numeric"
                value={minSalary}
                onChange={(e) => setMinSalary(e.target.value)}
                placeholder="Salario mínimo (USD)"
                title="Filtra los resultados ya cargados: no cambia la búsqueda en sí"
                className="col-span-2 rounded-lg border border-gray-300 px-3 py-2 text-sm text-gray-900 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 sm:col-span-1 sm:min-w-[160px] sm:flex-1"
              />
            </div>
            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-lg bg-brand-600 dark:bg-brand-200 dark:text-gray-950 px-4 py-2.5 text-sm font-semibold text-white hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto"
            >
              {loading ? "Buscando…" : "Buscar"}
            </button>
          </form>

          {error && <ErrorNotice message={error} />}

          {/* Something has to move while 15 providers are queried. A skeleton
              (not a spinner) because globals.css already argues the case: a
              spinner reads as "stuck", a skeleton reads as "your results are
              being laid out". The note underneath sets the expectation for a
              wait this long instead of leaving the user guessing. */}
          {loading && (
            <div className="space-y-3">
              <p className="text-center text-xs text-gray-400 dark:text-gray-500">
                Preguntando a todas las fuentes a la vez. Las lentas pueden tardar hasta un minuto.
              </p>
              <ListSkeleton rows={3} />
            </div>
          )}

          {sources.length > 0 && <SourcesSummary sources={sources} shownCount={results.length} />}

          {minSalaryValue && results.length > 0 && (
            <p className="text-xs text-gray-400 dark:text-gray-400">
              {filteredResults.length} de {results.length} muestran ${minSalaryValue.toLocaleString()}+ de
              salario (se ocultan los que no publican salario).
            </p>
          )}

          {/* Keyed by what came back, so a new search remounts the list and
              it starts at the first page again. Repeating the exact same
              search keeps your place, which is the behaviour you want when
              you tapped Buscar twice. */}
          <ResultsList
            key={`${filteredResults.length}:${filteredResults[0]?.external_id ?? ""}`}
            results={filteredResults}
            onImport={handleImport}
          />

          {!loading && searched && results.length > 0 && filteredResults.length === 0 && !error && (
            <p className="py-6 text-center text-sm text-gray-400 dark:text-gray-400">
              Nada cumple ese salario mínimo: prueba bajarlo.
            </p>
          )}

          {!loading && searched && results.length === 0 && !error && (
            <p className="py-6 text-center text-sm text-gray-400 dark:text-gray-400">
              No encontramos resultados: prueba otra palabra clave o quita el filtro de ubicación.
            </p>
          )}

          {!loading && !searched && (
            <p className="py-6 text-center text-sm text-gray-400 dark:text-gray-400">
              Elige un puesto y dale a Buscar. Luego toca «Agregar» en las que te interesen.
            </p>
          )}
        </div>
      </div>

      <ExternalPlatformsSection />
    </div>
  );
}

export default function DiscoverPage() {
  return (
    <RouteGuard>
      <DiscoverContent />
    </RouteGuard>
  );
}
