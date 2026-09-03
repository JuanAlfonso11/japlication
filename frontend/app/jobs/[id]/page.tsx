"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import RouteGuard from "@/components/RouteGuard";
import Spinner from "@/components/Spinner";
import ErrorNotice from "@/components/ErrorNotice";
import MatchBreakdown from "@/components/MatchBreakdown";
import ScoreBadge from "@/components/ScoreBadge";
import SkillTag from "@/components/SkillTag";
import { ApiError, jobsApi } from "@/lib/api";
import type { CoverLetter, Job, MatchResult, ResumeVersion } from "@/lib/types";

function resumeToPlainText(resume: ResumeVersion): string {
  const lines: string[] = [resume.title, ""];
  if (resume.content.summary) lines.push(resume.content.summary, "");
  if (resume.content.skills.length) {
    lines.push("SKILLS", resume.content.skills.join(", "), "");
  }
  if (resume.content.experience.length) {
    lines.push("EXPERIENCE");
    for (const entry of resume.content.experience) {
      const dates = [entry.start_date, entry.end_date ?? "Present"].filter(Boolean).join(" – ");
      lines.push(`${entry.title} — ${entry.company}${dates ? ` (${dates})` : ""}`);
      for (const bullet of entry.bullets) lines.push(`- ${bullet}`);
      lines.push("");
    }
  }
  if (resume.content.education.length) {
    lines.push("EDUCATION");
    for (const entry of resume.content.education) {
      lines.push(`${entry.degree}${entry.field ? `, ${entry.field}` : ""} — ${entry.institution}`);
    }
  }
  return lines.join("\n").trim();
}

function CopyButton({ text }: { text: string }) {
  const [copied, setCopied] = useState(false);

  async function handleCopy() {
    try {
      await navigator.clipboard.writeText(text);
      setCopied(true);
      setTimeout(() => setCopied(false), 1800);
    } catch {
      // clipboard API unavailable — no-op, user can select text manually.
    }
  }

  return (
    <button
      type="button"
      onClick={handleCopy}
      className="rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-semibold text-gray-600 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800"
    >
      {copied ? "Copied!" : "Copy to clipboard"}
    </button>
  );
}

function JobDetailContent() {
  const params = useParams<{ id: string }>();
  const jobId = params.id;

  const [job, setJob] = useState<Job | null>(null);
  const [match, setMatch] = useState<MatchResult | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  const [resume, setResume] = useState<ResumeVersion | null>(null);
  const [resumeLoading, setResumeLoading] = useState(false);
  const [resumeError, setResumeError] = useState<string | null>(null);

  const [coverLetter, setCoverLetter] = useState<CoverLetter | null>(null);
  const [coverLoading, setCoverLoading] = useState(false);
  const [coverError, setCoverError] = useState<string | null>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const data = await jobsApi.get(jobId);
      setJob(data);
      if (data.match) {
        setMatch(data.match);
      } else {
        try {
          const m = await jobsApi.match(jobId);
          setMatch(m);
        } catch {
          // Match may not be computable yet — non-fatal.
        }
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Failed to load this job.");
    } finally {
      setLoading(false);
    }
  }, [jobId]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleGenerateResume() {
    setResumeLoading(true);
    setResumeError(null);
    try {
      const res = await jobsApi.generateResume(jobId);
      setResume(res);
    } catch (err) {
      setResumeError(
        err instanceof ApiError ? err.message : "Could not generate a tailored resume."
      );
    } finally {
      setResumeLoading(false);
    }
  }

  async function handleGenerateCoverLetter() {
    setCoverLoading(true);
    setCoverError(null);
    try {
      const res = await jobsApi.generateCoverLetter(jobId, {
        resume_version_id: resume?.id,
      });
      setCoverLetter(res);
    } catch (err) {
      setCoverError(
        err instanceof ApiError ? err.message : "Could not generate a cover letter."
      );
    } finally {
      setCoverLoading(false);
    }
  }

  if (loading) return <Spinner label="Loading job…" />;
  if (error) return <ErrorNotice message={error} onRetry={load} />;
  if (!job) return null;

  return (
    <div className="space-y-6 pb-4 animate-fade-in">
      <div className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-gray-100 dark:bg-gray-900 dark:ring-gray-800">
        <div className="flex items-start justify-between gap-3">
          <div>
            <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">{job.title}</h1>
            <p className="text-sm text-gray-600 dark:text-gray-400">
              {job.company}
              {job.location ? ` · ${job.location}` : ""}
            </p>
            {job.source_url && (
              <a
                href={job.source_url}
                target="_blank"
                rel="noreferrer"
                className="mt-1 inline-block text-xs text-brand-600 hover:text-brand-700"
              >
                View original posting ↗
              </a>
            )}
          </div>
          {match && <ScoreBadge score={match.overall_score} size="lg" />}
        </div>

        {job.skills_required?.length > 0 && (
          <div className="mt-4 flex flex-wrap gap-1.5">
            {job.skills_required.map((s) => (
              <span
                key={s.name}
                className="rounded-full bg-gray-100 px-2.5 py-1 text-xs font-medium text-gray-600 dark:bg-gray-800 dark:text-gray-300"
              >
                {s.name}
              </span>
            ))}
          </div>
        )}
      </div>

      {match && (
        <div className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-gray-100 dark:bg-gray-900 dark:ring-gray-800">
          <h2 className="mb-3 font-semibold text-gray-900 dark:text-gray-100">Match breakdown</h2>
          <MatchBreakdown match={match} />
        </div>
      )}

      <div className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-gray-100 dark:bg-gray-900 dark:ring-gray-800">
        <h2 className="mb-2 font-semibold text-gray-900 dark:text-gray-100">Description</h2>
        <p className="whitespace-pre-line text-sm leading-relaxed text-gray-700 dark:text-gray-300">
          {job.description}
        </p>
      </div>

      {job.requirements?.length > 0 && (
        <div className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-gray-100 dark:bg-gray-900 dark:ring-gray-800">
          <h2 className="mb-2 font-semibold text-gray-900 dark:text-gray-100">Requirements</h2>
          <ul className="list-inside list-disc space-y-1 text-sm text-gray-700 dark:text-gray-300">
            {job.requirements.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </div>
      )}

      {job.responsibilities && job.responsibilities.length > 0 && (
        <div className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-gray-100 dark:bg-gray-900 dark:ring-gray-800">
          <h2 className="mb-2 font-semibold text-gray-900 dark:text-gray-100">Responsibilities</h2>
          <ul className="list-inside list-disc space-y-1 text-sm text-gray-700 dark:text-gray-300">
            {job.responsibilities.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-gray-100 dark:bg-gray-900 dark:ring-gray-800">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-semibold text-gray-900 dark:text-gray-100">Tailored resume</h2>
          <button
            type="button"
            onClick={handleGenerateResume}
            disabled={resumeLoading}
            className="rounded-lg bg-brand-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {resumeLoading ? "Generating…" : resume ? "Regenerate" : "Generate resume"}
          </button>
        </div>
        {resumeError && <ErrorNotice message={resumeError} />}
        {resume && (
          <div className="mt-2 space-y-3 rounded-xl border border-gray-100 bg-gray-50 p-4 dark:border-gray-800 dark:bg-gray-800/50">
            <div className="flex items-start justify-between gap-3">
              <div>
                <p className="font-semibold text-gray-900 dark:text-gray-100">{resume.title}</p>
                {resume.content.summary && (
                  <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">{resume.content.summary}</p>
                )}
              </div>
              <CopyButton text={resumeToPlainText(resume)} />
            </div>

            {resume.content.skills.length > 0 && (
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                  Skills
                </p>
                <div className="mt-1 flex flex-wrap gap-1.5">
                  {resume.content.skills.map((skill) => (
                    <SkillTag key={skill} label={skill} />
                  ))}
                </div>
              </div>
            )}

            {resume.content.experience.map((entry, i) => (
              <div key={i}>
                <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                  {entry.title} — {entry.company}
                </p>
                <ul className="mt-1 list-inside list-disc space-y-0.5 text-sm text-gray-700 dark:text-gray-300">
                  {entry.bullets.map((line, j) => (
                    <li key={j}>{line}</li>
                  ))}
                </ul>
              </div>
            ))}

            {resume.change_log.length > 0 && (
              <div className="border-t border-gray-200 pt-2 dark:border-gray-700">
                <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                  What changed
                </p>
                <ul className="mt-1 list-inside list-disc space-y-0.5 text-xs text-gray-500 dark:text-gray-400">
                  {resume.change_log.map((line, i) => (
                    <li key={i}>{line}</li>
                  ))}
                </ul>
              </div>
            )}
          </div>
        )}
      </div>

      <div className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-gray-100 dark:bg-gray-900 dark:ring-gray-800">
        <div className="mb-3 flex items-center justify-between">
          <h2 className="font-semibold text-gray-900 dark:text-gray-100">Cover letter</h2>
          <button
            type="button"
            onClick={handleGenerateCoverLetter}
            disabled={coverLoading}
            className="rounded-lg bg-brand-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {coverLoading ? "Generating…" : coverLetter ? "Regenerate" : "Generate cover letter"}
          </button>
        </div>
        {coverError && <ErrorNotice message={coverError} />}
        {coverLetter && (
          <div className="mt-2 space-y-3 rounded-xl border border-gray-100 bg-gray-50 p-4 dark:border-gray-800 dark:bg-gray-800/50">
            <div className="flex justify-end">
              <CopyButton text={coverLetter.content} />
            </div>
            <p className="whitespace-pre-line text-sm leading-relaxed text-gray-700 dark:text-gray-300">
              {coverLetter.content}
            </p>
          </div>
        )}
      </div>
    </div>
  );
}

export default function JobDetailPage() {
  return (
    <RouteGuard>
      <JobDetailContent />
    </RouteGuard>
  );
}
