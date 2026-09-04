"use client";

import { useState } from "react";
import RouteGuard from "@/components/RouteGuard";
import ErrorNotice from "@/components/ErrorNotice";
import ImportedJobCard from "@/components/ImportedJobCard";
import SkillTag from "@/components/SkillTag";
import { Select } from "@/components/ui/Field";
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
      setError(err instanceof ApiError ? err.message : "Could not add this job.");
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
    <div className="rounded-xl border border-gray-100 bg-white p-4 shadow-sm dark:border-gray-800 dark:bg-gray-900">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="mb-1 flex items-center gap-2">
            <SourceBadge source={result.source} />
            {result.seniority && <LevelBadge level={result.seniority} />}
          </div>
          <h3 className="font-semibold text-gray-900 dark:text-gray-100">{result.title}</h3>
          <p className="text-sm text-gray-600 dark:text-gray-400">
            {result.company}
            {result.location ? ` · ${result.location}` : ""}
          </p>
          {(budget || result.posted_at_text) && (
            <p className="mt-0.5 text-xs text-gray-400 dark:text-gray-500">
              {budget}
              {budget && result.posted_at_text ? " · " : ""}
              {result.posted_at_text}
            </p>
          )}
        </div>
        <button
          type="button"
          onClick={handleImport}
          disabled={loading || imported}
          className="shrink-0 rounded-lg bg-brand-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {imported ? "Added ✓" : loading ? "Adding…" : "Add to queue"}
        </button>
      </div>
      {result.skills_required?.length > 0 && (
        <div className="mt-2 flex flex-wrap gap-1.5">
          {result.skills_required.slice(0, 8).map((s) => (
            <SkillTag key={s.name} label={s.name} />
          ))}
        </div>
      )}
      {error && <p className="mt-2 text-xs text-rose-600 dark:text-rose-400">{error}</p>}
    </div>
  );
}

function SourcesSummary({ sources }: { sources: AggregateSourceStatus[] }) {
  const failed = sources.filter((s) => s.error);
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-xs text-gray-400 dark:text-gray-500">
      {sources.map((s) => (
        <span
          key={s.provider}
          className={`rounded-full px-2 py-0.5 ${
            s.error
              ? "bg-rose-50 text-rose-600 dark:bg-rose-900/30 dark:text-rose-400"
              : "bg-gray-50 text-gray-500 dark:bg-gray-800 dark:text-gray-400"
          }`}
          title={s.error ?? undefined}
        >
          {PROVIDER_LABELS[s.provider] ?? s.provider}: {s.error ? "error" : s.count}
        </span>
      ))}
      {failed.length > 0 && (
        <span className="text-rose-500 dark:text-rose-400">
          {failed.length} fuente{failed.length > 1 ? "s" : ""} no respondió — el resto de resultados sigue completo.
        </span>
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
            No tienen API pública, así que no aparecen en la búsqueda de arriba — pero son buenas opciones
            para revisar y aplicar manualmente desde RD.
          </p>
        </div>
        <span className="shrink-0 text-gray-400 dark:text-gray-500">{open ? "−" : "+"}</span>
      </button>
      {open && (
        <div className="mt-4 space-y-4">
          {EXTERNAL_PLATFORM_GROUPS.map((group) => (
            <div key={group.label}>
              <h3 className="mb-1.5 text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">
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
      setError(err instanceof ApiError ? err.message : "Search failed.");
    } finally {
      setLoading(false);
    }
  }

  async function handleImport(result: ExternalJobResult) {
    const job = await jobsApi.importExternal({ source: result.source, external_id: result.external_id });
    setLastAdded(await importAndMatch(job));
  }

  return (
    <div className="space-y-6 pb-4 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Discover jobs</h1>
        <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
          Busca a la vez en 12 fuentes (9 públicas sin login + Adzuna/USAJobs/France Travail si
          configuraste sus claves) y combina los resultados en una sola lista. Todo lo que agregues
          queda comparado contra tu perfil en Home.
        </p>
      </div>

      <div className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-gray-100 dark:bg-gray-900 dark:ring-gray-800">
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
            </div>
            <button
              type="submit"
              disabled={loading}
              className="w-full rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto"
            >
              {loading ? "Searching…" : "Search"}
            </button>
          </form>

          {error && <ErrorNotice message={error} />}

          {sources.length > 0 && <SourcesSummary sources={sources} />}

          <div className="space-y-3">
            {results.map((r) => (
              <ExternalResultCard key={`${r.source}:${r.external_id}`} result={r} onImport={handleImport} />
            ))}
          </div>

          {!loading && searched && results.length === 0 && !error && (
            <p className="py-6 text-center text-sm text-gray-400 dark:text-gray-500">
              No encontramos resultados — prueba otra palabra clave o quita el filtro de ubicación.
            </p>
          )}

          {!loading && !searched && (
            <p className="py-6 text-center text-sm text-gray-400 dark:text-gray-500">
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
