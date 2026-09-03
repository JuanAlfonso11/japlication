"use client";

import { useState } from "react";
import RouteGuard from "@/components/RouteGuard";
import ErrorNotice from "@/components/ErrorNotice";
import ImportedJobCard from "@/components/ImportedJobCard";
import SkillTag from "@/components/SkillTag";
import { ApiError, jobsApi } from "@/lib/api";
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
    <span className="inline-flex items-center rounded-full bg-gray-100 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-gray-500">
      {PROVIDER_LABELS[source] ?? source}
    </span>
  );
}

function LevelBadge({ level }: { level: string }) {
  const label = EXPERIENCE_LEVEL_LABELS[level as ExperienceLevel] ?? level;
  return (
    <span className="inline-flex items-center rounded-full bg-brand-50 px-2 py-0.5 text-[11px] font-semibold uppercase tracking-wide text-brand-700">
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
    <div className="rounded-xl border border-gray-100 bg-white p-4 shadow-sm">
      <div className="flex items-start justify-between gap-3">
        <div>
          <div className="mb-1 flex items-center gap-2">
            <SourceBadge source={result.source} />
            {result.seniority && <LevelBadge level={result.seniority} />}
          </div>
          <h3 className="font-semibold text-gray-900">{result.title}</h3>
          <p className="text-sm text-gray-600">
            {result.company}
            {result.location ? ` · ${result.location}` : ""}
          </p>
          {(budget || result.posted_at_text) && (
            <p className="mt-0.5 text-xs text-gray-400">
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
      {error && <p className="mt-2 text-xs text-rose-600">{error}</p>}
    </div>
  );
}

function SourcesSummary({ sources }: { sources: AggregateSourceStatus[] }) {
  const failed = sources.filter((s) => s.error);
  return (
    <div className="flex flex-wrap items-center gap-1.5 text-xs text-gray-400">
      {sources.map((s) => (
        <span
          key={s.provider}
          className={`rounded-full px-2 py-0.5 ${
            s.error ? "bg-rose-50 text-rose-600" : "bg-gray-50 text-gray-500"
          }`}
          title={s.error ?? undefined}
        >
          {PROVIDER_LABELS[s.provider] ?? s.provider}: {s.error ? "error" : s.count}
        </span>
      ))}
      {failed.length > 0 && (
        <span className="text-rose-500">
          {failed.length} fuente{failed.length > 1 ? "s" : ""} no respondió — el resto de resultados sigue completo.
        </span>
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
        <h1 className="text-2xl font-bold text-gray-900">Discover jobs</h1>
        <p className="mt-1 text-sm text-gray-500">
          Busca a la vez en 6 APIs públicas sin login (Himalayas, Arbeitnow, Remotive, Jobicy,
          RemoteJobs.org y The Muse) y combina los resultados en una sola lista. Anything you add
          shows up matched against your profile back on Home.
        </p>
      </div>

      <div className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-gray-100">
        <div className="space-y-4">
          <form onSubmit={handleSubmit} className="flex flex-wrap gap-2">
            <select
              value={q}
              onChange={(e) => setQ(e.target.value)}
              className="min-w-[200px] flex-1 rounded-lg border border-gray-300 px-3 py-2.5 text-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
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
            </select>
            <select
              value={location}
              onChange={(e) => setLocation(e.target.value)}
              className="min-w-[160px] rounded-lg border border-gray-300 px-3 py-2.5 text-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
            >
              <option value="">Cualquier ubicación</option>
              {LOCATION_OPTIONS.map((loc) => (
                <option key={loc} value={loc}>
                  {loc}
                </option>
              ))}
            </select>
            <select
              value={remoteType}
              onChange={(e) => setRemoteType(e.target.value as RemoteType | "")}
              className="min-w-[150px] rounded-lg border border-gray-300 px-3 py-2.5 text-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
            >
              <option value="">Cualquier modalidad</option>
              {REMOTE_TYPES.map((rt) => (
                <option key={rt} value={rt}>
                  {REMOTE_TYPE_LABELS[rt]}
                </option>
              ))}
            </select>
            <select
              value={experienceLevelFilter}
              onChange={(e) => setExperienceLevelFilter(e.target.value as ExperienceLevel | "")}
              className="min-w-[170px] rounded-lg border border-gray-300 px-3 py-2.5 text-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
            >
              <option value="">Cualquier nivel</option>
              {EXPERIENCE_LEVELS.map((lvl) => (
                <option key={lvl} value={lvl}>
                  {EXPERIENCE_LEVEL_LABELS[lvl]}
                </option>
              ))}
            </select>
            <button
              type="submit"
              disabled={loading}
              className="rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60"
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
            <p className="py-6 text-center text-sm text-gray-400">
              No encontramos resultados — prueba otra palabra clave o quita el filtro de ubicación.
            </p>
          )}

          {!loading && !searched && (
            <p className="py-6 text-center text-sm text-gray-400">
              Busca algo para ver resultados combinados de las 6 fuentes sin login.
            </p>
          )}
        </div>
      </div>

      {lastAdded && <ImportedJobCard job={lastAdded} />}
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
