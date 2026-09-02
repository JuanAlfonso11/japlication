"use client";

import Link from "next/link";
import { useState } from "react";
import RouteGuard from "@/components/RouteGuard";
import ErrorNotice from "@/components/ErrorNotice";
import SkillTag from "@/components/SkillTag";
import { ApiError, jobsApi } from "@/lib/api";
import type { Job } from "@/lib/types";

function ImportedJobCard({ job }: { job: Job }) {
  return (
    <div className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-gray-100 animate-fade-in">
      <p className="text-xs font-semibold uppercase tracking-wide text-emerald-600">
        Imported successfully
      </p>
      <h2 className="mt-1 text-xl font-bold text-gray-900">{job.title}</h2>
      <p className="text-sm text-gray-600">
        {job.company}
        {job.location ? ` · ${job.location}` : ""}
      </p>

      {job.skills?.length > 0 && (
        <div className="mt-3 flex flex-wrap gap-1.5">
          {job.skills.slice(0, 12).map((s) => (
            <SkillTag key={s} label={s} />
          ))}
        </div>
      )}

      {job.requirements?.length > 0 && (
        <div className="mt-4">
          <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-gray-500">
            Requirements
          </p>
          <ul className="list-inside list-disc space-y-1 text-sm text-gray-700">
            {job.requirements.slice(0, 6).map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </div>
      )}

      <Link
        href={`/jobs/${job.id}`}
        className="mt-4 inline-flex items-center gap-1 rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700"
      >
        View job details
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M5 12h14M13 5l7 7-7 7" /></svg>
      </Link>
    </div>
  );
}

function ImportByUrl({ onImported }: { onImported: (job: Job) => void }) {
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const job = await jobsApi.import({ url });
      onImported(job);
      setUrl("");
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "Could not import that job posting."
      );
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      {error && <ErrorNotice message={error} />}
      <label className="block">
        <span className="mb-1 block text-xs font-medium text-gray-600">Job posting URL</span>
        <input
          type="url"
          required
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://company.com/careers/senior-engineer"
          className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100"
        />
      </label>
      <button
        type="submit"
        disabled={loading}
        className="w-full rounded-lg bg-brand-600 px-4 py-2.5 font-semibold text-white hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto"
      >
        {loading ? "Importing…" : "Import job"}
      </button>
    </form>
  );
}

function ManualJobForm({ onImported }: { onImported: (job: Job) => void }) {
  const [title, setTitle] = useState("");
  const [company, setCompany] = useState("");
  const [location, setLocation] = useState("");
  const [description, setDescription] = useState("");
  const [requirements, setRequirements] = useState("");
  const [skills, setSkills] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const job = await jobsApi.create({
        title,
        company,
        location,
        description,
        requirements: requirements
          .split("\n")
          .map((r) => r.trim())
          .filter(Boolean),
        skills: skills
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean),
      });
      onImported(job);
      setTitle("");
      setCompany("");
      setLocation("");
      setDescription("");
      setRequirements("");
      setSkills("");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not save that job.");
    } finally {
      setLoading(false);
    }
  }

  const fieldClass =
    "w-full rounded-lg border border-gray-300 px-3 py-2.5 text-sm outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100";

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      {error && <ErrorNotice message={error} />}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label className="block">
          <span className="mb-1 block text-xs font-medium text-gray-600">Title</span>
          <input required className={fieldClass} value={title} onChange={(e) => setTitle(e.target.value)} />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs font-medium text-gray-600">Company</span>
          <input required className={fieldClass} value={company} onChange={(e) => setCompany(e.target.value)} />
        </label>
        <label className="block sm:col-span-2">
          <span className="mb-1 block text-xs font-medium text-gray-600">Location</span>
          <input className={fieldClass} value={location} onChange={(e) => setLocation(e.target.value)} />
        </label>
      </div>
      <label className="block">
        <span className="mb-1 block text-xs font-medium text-gray-600">Full description</span>
        <textarea
          required
          className={`${fieldClass} min-h-[120px]`}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Paste the full job description text here…"
        />
      </label>
      <label className="block">
        <span className="mb-1 block text-xs font-medium text-gray-600">
          Requirements (one per line)
        </span>
        <textarea
          className={`${fieldClass} min-h-[90px]`}
          value={requirements}
          onChange={(e) => setRequirements(e.target.value)}
          placeholder={"5+ years of backend development\nExperience with distributed systems"}
        />
      </label>
      <label className="block">
        <span className="mb-1 block text-xs font-medium text-gray-600">
          Skills (comma-separated)
        </span>
        <input
          className={fieldClass}
          value={skills}
          onChange={(e) => setSkills(e.target.value)}
          placeholder="C#, SQL, Kubernetes"
        />
      </label>
      <button
        type="submit"
        disabled={loading}
        className="w-full rounded-lg bg-brand-600 px-4 py-2.5 font-semibold text-white hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto"
      >
        {loading ? "Saving…" : "Add job"}
      </button>
    </form>
  );
}

function ImportContent() {
  const [mode, setMode] = useState<"url" | "manual">("url");
  const [lastImported, setLastImported] = useState<Job | null>(null);

  return (
    <div className="space-y-6 pb-4 animate-fade-in">
      <div>
        <h1 className="text-2xl font-bold text-gray-900">Import a job</h1>
        <p className="mt-1 text-sm text-gray-500">
          Paste a posting URL and JobFlow AI will parse it into a structured job you can match
          against.
        </p>
      </div>

      <div className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-gray-100">
        <div className="mb-4 inline-flex rounded-lg bg-gray-100 p-1 text-sm font-medium">
          <button
            type="button"
            onClick={() => setMode("url")}
            className={`rounded-md px-3 py-1.5 transition-colors ${
              mode === "url" ? "bg-white shadow-sm text-gray-900" : "text-gray-500"
            }`}
          >
            From URL
          </button>
          <button
            type="button"
            onClick={() => setMode("manual")}
            className={`rounded-md px-3 py-1.5 transition-colors ${
              mode === "manual" ? "bg-white shadow-sm text-gray-900" : "text-gray-500"
            }`}
          >
            Paste manually
          </button>
        </div>

        {mode === "url" ? (
          <ImportByUrl onImported={setLastImported} />
        ) : (
          <ManualJobForm onImported={setLastImported} />
        )}
      </div>

      {lastImported && <ImportedJobCard job={lastImported} />}
    </div>
  );
}

export default function ImportJobPage() {
  return (
    <RouteGuard>
      <ImportContent />
    </RouteGuard>
  );
}
