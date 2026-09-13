"use client";

import { useMemo, useState } from "react";
import RouteGuard from "@/components/RouteGuard";
import ErrorNotice from "@/components/ErrorNotice";
import ImportedJobCard from "@/components/ImportedJobCard";
import SkillTag from "@/components/SkillTag";
import { Select } from "@/components/ui/Field";
import Button from "@/components/ui/Button";
import PageHeader from "@/components/ui/PageHeader";
import { ApiError, jobsApi } from "@/lib/api";
import { EXTERNAL_PLATFORM_GROUPS } from "@/lib/externalPlatforms";
import { importAndMatch } from "@/lib/jobActions";
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
  type Job,
  type RemoteType,
} from "@/lib/types";

const EXPERIENCE_LEVELS: ExperienceLevel[] = ["internship", "entry", "mid", "senior", "lead"];
const REMOTE_TYPES: RemoteType[] = ["remote", "hybrid", "onsite"];

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
  onImport: (result: ExternalJobResult) => Promise<void>;
}) {
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [imported, setImported] = useState(false);

  async function handleImport() {
    setLoading(true);
    setError(null);
    try {
      await onImport(result);
      setImported(true);
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
        <Button
          size="sm"
          variant={imported ? "secondary" : "primary"}
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
        {pending.length > 0 && (
          <span
            className="rounded-full bg-gray-100 px-2.5 py-1 font-semibold text-gray-600 dark:bg-gray-800 dark:text-gray-300"
            title={pending[0].error ?? undefined}
          >
            {pending.map((s) => PROVIDER_LABELS[s.provider] ?? s.provider).join(", ")} buscando…
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

function DiscoverContent() {
  const [q, setQ] = useState("");
  const [location, setLocation] = useState("");
  const [remoteType, setRemoteType] = useState<RemoteType | "">("remote");
  const [experienceLevelFilter, setExperienceLevelFilter] = useState<ExperienceLevel | "">("");
  const [minSalary, setMinSalary] = useState("");
  const [results, setResults] = useState<ExternalJobResult[]>([]);
  const [sources, setSources] = useState<AggregateSourceStatus[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [lastAdded, setLastAdded] = useState<Job | null>(null);
  const [searched, setSearched] = useState(false);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setLoading(true);
    setError(null);
    setLastAdded(null);
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
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Falló la búsqueda.");
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

  async function handleImport(result: ExternalJobResult) {
    const job = await jobsApi.importExternal({ source: result.source, external_id: result.external_id });
    setLastAdded(await importAndMatch(job));
  }

  return (
    <div className="space-y-6 pb-4 animate-fade-in">
      <PageHeader
        title="Buscar trabajos"
        subtitle="Busca en 15 fuentes a la vez, LinkedIn incluido, y combina todo en una sola lista, sin repetidos. Lo que agregues se compara contra tu perfil en Inicio."
      />

      <div className="rounded-2xl bg-white p-5 shadow-soft ring-1 ring-gray-100 dark:bg-gray-900 dark:ring-gray-800">
        <div className="space-y-4">
          <form onSubmit={handleSubmit} className="space-y-2">
            <div className="grid grid-cols-2 gap-2 sm:flex sm:flex-wrap">
              <Select
                value={q}
                onChange={(e) => setQ(e.target.value)}
                className="col-span-2 sm:min-w-[180px] sm:flex-1"
              >
                <option value="">Cualquier puesto</option>
                {JOB_TITLE_GROUPS.map((group) => (
                  <optgroup key={group.label} label={group.label}>
                    {group.options.map((title) => (
                      <option key={title} value={title}>
                        {title}
                      </option>
                    ))}
                  </optgroup>
                ))}
              </Select>
              <Select
                value={location}
                onChange={(e) => setLocation(e.target.value)}
                className="sm:min-w-[160px] sm:flex-1"
              >
                <option value="">Cualquier ubicación</option>
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
                <option value="">Cualquier modalidad</option>
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
                <option value="">Cualquier nivel</option>
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
              className="w-full rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto"
            >
              {loading ? "Buscando…" : "Buscar"}
            </button>
          </form>

          {error && <ErrorNotice message={error} />}

          {sources.length > 0 && <SourcesSummary sources={sources} shownCount={results.length} />}

          {minSalaryValue && results.length > 0 && (
            <p className="text-xs text-gray-400 dark:text-gray-400">
              {filteredResults.length} de {results.length} muestran ${minSalaryValue.toLocaleString()}+ de
              salario (se ocultan los que no publican salario).
            </p>
          )}

          <div className="space-y-3">
            {filteredResults.map((r) => (
              <ExternalResultCard key={`${r.source}:${r.external_id}`} result={r} onImport={handleImport} />
            ))}
          </div>

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
              Busca algo para ver resultados combinados de todas las fuentes sin login.
            </p>
          )}
        </div>
      </div>

      {lastAdded && <ImportedJobCard job={lastAdded} />}

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
