"use client";

import { Suspense, useCallback, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import RouteGuard from "@/components/RouteGuard";
import ErrorNotice from "@/components/ErrorNotice";
import ImportedJobCard from "@/components/ImportedJobCard";
import SkillTag from "@/components/SkillTag";
import { ApiError, integrationsApi, jobsApi } from "@/lib/api";
import { importAndMatch } from "@/lib/jobActions";
import type { ExternalJobResult, ExternalProvider, Job, UpworkStatus } from "@/lib/types";

const PROVIDERS: { id: ExternalProvider; label: string; hint: string }[] = [
  { id: "himalayas", label: "Himalayas", hint: "Free, remote jobs, no setup" },
  { id: "google_jobs", label: "Google Jobs", hint: "Needs SERPAPI_API_KEY" },
  { id: "upwork", label: "Upwork", hint: "Freelance — connect your account" },
];

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

function UpworkConnectPanel({ status }: { status: UpworkStatus }) {
  const [connecting, setConnecting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  if (!status.configured) {
    return (
      <p className="rounded-lg bg-gray-50 p-4 text-sm text-gray-500">
        Upwork search isn&apos;t configured on this server yet. Register an app at{" "}
        <a
          className="text-brand-600 hover:underline"
          href="https://www.upwork.com/developer/apps"
          target="_blank"
          rel="noreferrer"
        >
          upwork.com/developer/apps
        </a>{" "}
        and set <code className="rounded bg-gray-100 px-1 py-0.5">UPWORK_CLIENT_ID</code> /{" "}
        <code className="rounded bg-gray-100 px-1 py-0.5">UPWORK_CLIENT_SECRET</code> in the backend&apos;s
        .env.
      </p>
    );
  }

  async function handleConnect() {
    setConnecting(true);
    setError(null);
    try {
      const { authorization_url } = await integrationsApi.upworkAuthorize();
      window.location.href = authorization_url;
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not start the Upwork connection.");
      setConnecting(false);
    }
  }

  return (
    <div className="rounded-lg bg-gray-50 p-4">
      {error && <ErrorNotice message={error} />}
      <p className="mb-3 text-sm text-gray-600">
        Connect your Upwork account to search live freelance postings.
      </p>
      <button
        type="button"
        onClick={handleConnect}
        disabled={connecting}
        className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-60"
      >
        {connecting ? "Redirecting…" : "Connect Upwork"}
      </button>
    </div>
  );
}

function UpworkCallbackBanner() {
  const searchParams = useSearchParams();
  const upworkParam = searchParams.get("upwork");
  if (!upworkParam) return null;
  if (upworkParam === "connected") {
    return (
      <div className="rounded-lg bg-emerald-50 px-4 py-3 text-sm text-emerald-700 ring-1 ring-inset ring-emerald-600/20">
        Upwork connected — you can search live freelance postings now.
      </div>
    );
  }
  return (
    <div className="rounded-lg bg-rose-50 px-4 py-3 text-sm text-rose-700 ring-1 ring-inset ring-rose-600/20">
      Couldn&apos;t connect your Upwork account. Please try again.
    </div>
  );
}

function DiscoverContent() {
  const [provider, setProvider] = useState<ExternalProvider>("himalayas");
  const [q, setQ] = useState("");
  const [location, setLocation] = useState("");
  const [results, setResults] = useState<ExternalJobResult[]>([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hasMore, setHasMore] = useState(false);
  const [nextPageToken, setNextPageToken] = useState<string | undefined>();
  const [nextPage, setNextPage] = useState<number | undefined>();
  const [upworkStatus, setUpworkStatus] = useState<UpworkStatus | null>(null);
  const [lastAdded, setLastAdded] = useState<Job | null>(null);

  const refreshUpworkStatus = useCallback(() => {
    integrationsApi
      .upworkStatus()
      .then(setUpworkStatus)
      .catch(() => setUpworkStatus({ connected: false, configured: false }));
  }, []);

  useEffect(() => {
    if (provider === "upwork") refreshUpworkStatus();
  }, [provider, refreshUpworkStatus]);

  async function runSearch(reset: boolean) {
    setLoading(true);
    setError(null);
    try {
      const data = await jobsApi.search({
        provider,
        q: q || undefined,
        location: provider === "google_jobs" ? location || undefined : undefined,
        country: provider === "himalayas" ? location || undefined : undefined,
        next_page_token: reset ? undefined : nextPageToken,
        page: reset ? undefined : nextPage,
      });
      setResults((prev) => (reset ? data.results : [...prev, ...data.results]));
      setHasMore(data.has_more);
      setNextPageToken(data.next_page_token ?? undefined);
      setNextPage(data.page ?? undefined);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Search failed.");
    } finally {
      setLoading(false);
    }
  }

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setResults([]);
    setLastAdded(null);
    await runSearch(true);
  }

  async function handleImport(result: ExternalJobResult) {
    const job = await jobsApi.importExternal({ source: result.source, external_id: result.external_id });
    setLastAdded(await importAndMatch(job));
  }

  const showForm = provider !== "upwork" || upworkStatus?.connected;

  return (
    <div className="space-y-6 pb-4 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Discover jobs</h1>
        <p className="mt-1 text-sm text-gray-500">
          Search live listings from Himalayas, Google Jobs, or Upwork. Anything you add shows up
          matched against your profile back on Home.
        </p>
      </div>

      <Suspense fallback={null}>
        <UpworkCallbackBanner />
      </Suspense>

      <div className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-gray-100">
        <div className="space-y-4">
          <div className="flex flex-wrap gap-2">
            {PROVIDERS.map((p) => (
              <button
                key={p.id}
                type="button"
                onClick={() => {
                  setProvider(p.id);
                  setResults([]);
                  setError(null);
                }}
                className={`rounded-lg border px-3 py-2 text-left text-sm transition-colors ${
                  provider === p.id
                    ? "border-brand-500 bg-brand-50 text-brand-700"
                    : "border-gray-200 text-gray-600 hover:border-gray-300"
                }`}
              >
                <span className="block font-semibold">{p.label}</span>
                <span className="block text-xs text-gray-400">{p.hint}</span>
              </button>
            ))}
          </div>

          {provider === "upwork" && upworkStatus && !upworkStatus.connected && (
            <UpworkConnectPanel status={upworkStatus} />
          )}

          {showForm && (
            <>
              <form onSubmit={handleSubmit} className="flex flex-wrap gap-2">
                <input
                  type="text"
                  value={q}
                  onChange={(e) => setQ(e.target.value)}
                  placeholder={
                    provider === "upwork" ? "Skills or title, e.g. Django, React" : "Job title or keywords"
                  }
                  className="min-w-[200px] flex-1 rounded-lg border border-gray-300 px-3 py-2.5 text-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
                />
                {provider !== "upwork" && (
                  <input
                    type="text"
                    value={location}
                    onChange={(e) => setLocation(e.target.value)}
                    placeholder={provider === "himalayas" ? "Country (optional)" : "Location (optional)"}
                    className="min-w-[160px] flex-1 rounded-lg border border-gray-300 px-3 py-2.5 text-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
                  />
                )}
                <button
                  type="submit"
                  disabled={loading}
                  className="rounded-lg bg-brand-600 px-4 py-2.5 text-sm font-semibold text-white hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60"
                >
                  {loading ? "Searching…" : "Search"}
                </button>
              </form>

              {error && <ErrorNotice message={error} />}

              <div className="space-y-3">
                {results.map((r) => (
                  <ExternalResultCard key={r.external_id} result={r} onImport={handleImport} />
                ))}
              </div>

              {hasMore && results.length > 0 && (
                <button
                  type="button"
                  onClick={() => runSearch(false)}
                  disabled={loading}
                  className="w-full rounded-lg border border-gray-200 py-2 text-sm font-medium text-gray-600 hover:bg-gray-50 disabled:opacity-60"
                >
                  {loading ? "Loading…" : "Load more"}
                </button>
              )}

              {!loading && results.length === 0 && !error && (
                <p className="py-6 text-center text-sm text-gray-400">
                  Search {PROVIDERS.find((p) => p.id === provider)?.label} to see live results here.
                </p>
              )}
            </>
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
