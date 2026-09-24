"use client";

import AtsCheckPanel from "@/components/AtsCheckPanel";
import EmailApplyPanel from "@/components/EmailApplyPanel";
import DeadlineBadge from "@/components/DeadlineBadge";
import WorkAuthBadge, { ClosedBadge } from "@/components/WorkAuthBadge";
import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import RouteGuard from "@/components/RouteGuard";
import CollapsibleText from "@/components/CollapsibleText";
import { ListSkeleton } from "@/components/ui/Skeleton";
import Link from "next/link";
import Button, { buttonClass } from "@/components/ui/Button";
import ErrorNotice from "@/components/ErrorNotice";
import MatchBreakdown from "@/components/MatchBreakdown";
import ScoreBadge from "@/components/ScoreBadge";
import SkillTag from "@/components/SkillTag";
import ApplicationKit from "@/components/ApplicationKit";
import ResumeEditor from "@/components/ResumeEditor";
import InterviewPrepCard from "@/components/InterviewPrepCard";
import { ApiError, coverLetterApi, jobsApi, resumeApi } from "@/lib/api";
import { describeSave, exportLatex, safeFilename } from "@/lib/cvExport";
import { isNativeApp } from "@/lib/platform";
import type {
  CoverLetter,
  Job,
  MatchResult,
  ProfileLanguage,
  ResumeVersion,
  ReusableResumeSuggestion,
} from "@/lib/types";

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
      {copied ? "¡Copiado!" : "Copiar al portapapeles"}
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
  // null = "match the posting": the server detects the ad's language.
  // An explicit choice is for the case the default gets wrong, e.g. a
  // Spanish-language ad at a company whose hiring team reads English.
  const [resumeLanguage, setResumeLanguage] = useState<ProfileLanguage | null>(null);
  const [resumeError, setResumeError] = useState<string | null>(null);
  const [editingResume, setEditingResume] = useState(false);
  const [reusable, setReusable] = useState<ReusableResumeSuggestion | null>(null);
  const [pdfDownloading, setPdfDownloading] = useState(false);
  const [overleafOpening, setOverleafOpening] = useState(false);
  // Read once on mount: the server render has no window, so calling it
  // during render would disagree with the first client render.
  const [nativeApp, setNativeApp] = useState(false);
  useEffect(() => setNativeApp(isNativeApp()), []);
  const [pdfError, setPdfError] = useState<string | null>(null);
  // Where the last export landed. A browser announces its own downloads;
  // a phone announces nothing, so the app has to.
  const [saveNotice, setSaveNotice] = useState<string | null>(null);
  const [coverPdfDownloading, setCoverPdfDownloading] = useState(false);
  const [coverPdfError, setCoverPdfError] = useState<string | null>(null);
  const [coverSaveNotice, setCoverSaveNotice] = useState<string | null>(null);

  const [coverLetter, setCoverLetter] = useState<CoverLetter | null>(null);
  const [coverLoading, setCoverLoading] = useState(false);
  const [coverError, setCoverError] = useState<string | null>(null);

  const [applying, setApplying] = useState(false);
  const [applyError, setApplyError] = useState<string | null>(null);
  const [applied, setApplied] = useState(false);
  const [applyNotice, setApplyNotice] = useState<string | null>(null);
  // No saved profile: nothing to score against and nothing to build a CV
  // from. "Aplicar" used to open the employer's page anyway, then fail to
  // generate the CV and never record the application.
  const [noProfile, setNoProfile] = useState(false);
  const [savingToPipeline, setSavingToPipeline] = useState(false);

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
        } catch (err) {
          // 400 = no profile yet; anything else is non-fatal.
          if (err instanceof ApiError && err.status === 400) setNoProfile(true);
        }
      }
      try {
        const suggestion = await jobsApi.reusableResume(jobId);
        if (suggestion.resume_version) setReusable(suggestion);
      } catch {
        // Reuse suggestion is a nice-to-have — never blocks the page.
      }
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo cargar este trabajo.");
    } finally {
      setLoading(false);
    }
  }, [jobId]);

  useEffect(() => {
    load();
  }, [load]);

  async function handleDownloadPdf() {
    if (!resume) return;
    setPdfDownloading(true);
    setPdfError(null);
    setSaveNotice(null);
    try {
      const outcome = await resumeApi.downloadPdf(
        resume.id,
        `${safeFilename(job?.title ?? "resume")}.pdf`
      );
      setSaveNotice(describeSave(outcome, "PDF"));
    } catch (err) {
      setPdfError(err instanceof ApiError ? err.message : "No se pudo descargar el PDF.");
    } finally {
      setPdfDownloading(false);
    }
  }

  /** In a browser this opens Overleaf; in the Android app it saves the .tex,
   * because the WebView drops the POST body Overleaf needs. The full reason
   * lives with the shared helper — exportLatex in lib/cvExport.ts — which the
   * master CV's download buttons use as well. */
  async function handleLatexExport() {
    if (!resume) return;
    setOverleafOpening(true);
    setPdfError(null);
    setSaveNotice(null);
    try {
      setSaveNotice(
        await exportLatex({
          label: `CV - ${job?.title ?? "JobPilot"}`,
          getSource: () => resumeApi.latexSource(resume.id),
          download: (filename) => resumeApi.downloadTex(resume.id, filename),
        })
      );
    } catch (err) {
      setPdfError(
        err instanceof ApiError ? err.message : "No se pudo exportar el CV en LaTeX."
      );
    } finally {
      setOverleafOpening(false);
    }
  }

  async function handleDownloadCoverLetterPdf() {
    if (!coverLetter) return;
    setCoverPdfDownloading(true);
    setCoverPdfError(null);
    setCoverSaveNotice(null);
    try {
      const outcome = await coverLetterApi.downloadPdf(
        coverLetter.id,
        `${safeFilename(`Cover letter - ${job?.title ?? "job"}`)}.pdf`
      );
      setCoverSaveNotice(describeSave(outcome, "Carta en PDF"));
    } catch (err) {
      setCoverPdfError(err instanceof ApiError ? err.message : "No se pudo descargar el PDF.");
    } finally {
      setCoverPdfDownloading(false);
    }
  }

  function handleReuseResume() {
    if (reusable?.resume_version) {
      setResume(reusable.resume_version);
      setReusable(null);
    }
  }

  async function handleApply() {
    // Opened synchronously, before any `await`, so the browser still
    // counts this as "triggered by a user gesture" and doesn't block it —
    // once we've awaited anything, some browsers (Safari especially) treat
    // a later window.open() as an unrequested popup and kill it.
    // El formulario real cuando está resuelto; si no, el listado como antes.
    // Ninguna source_url apunta al formulario -- todas al listado del portal,
    // un salto antes -- así que esto ahorra buscar el botón cada vez.
    const destino = job?.apply_url ?? job?.source_url;
    if (destino) window.open(destino, "_blank", "noopener,noreferrer");

    setApplying(true);
    setApplyError(null);
    setApplyNotice(null);
    try {
      let activeResume = resume;
      if (!activeResume) {
        try {
          activeResume = await jobsApi.generateResume(jobId, resumeLanguage ? { language: resumeLanguage } : undefined);
          setResume(activeResume);
        } catch (err) {
          // The employer's page is already open, so the user IS applying:
          // record it anyway rather than losing the application.
          setApplyNotice(
            `No pudimos preparar tu CV (${
              err instanceof ApiError ? err.message : "error de conexión"
            }). Igual la registramos como aplicada.`
          );
        }
      }
      if (activeResume) {
        try {
          await resumeApi.downloadPdf(activeResume.id, `${job?.title ?? "resume"}.pdf`.replace(/[/\\?%*:|"<>]/g, "-"));
        } catch {
          // The PDF is a convenience, not a prerequisite — a failed download
          // (e.g. a flaky connection) shouldn't block recording the
          // application or opening the real posting, which already happened.
        }
      }
      await jobsApi.decide(jobId, {
        decision: "right",
        resume_version_id: activeResume?.id,
        cover_letter_id: coverLetter?.id,
        // This button already opened the employer's posting, so this is a
        // real application — unlike a right swipe on Home, which only saves.
        mark_applied: true,
      });
      setApplied(true);
    } catch (err) {
      setApplyError(err instanceof ApiError ? err.message : "No se pudo enviar la aplicación.");
    } finally {
      setApplying(false);
    }
  }

  async function handleSaveToPipeline() {
    setSavingToPipeline(true);
    setApplyError(null);
    try {
      await jobsApi.decide(jobId, { decision: "right" });
      setApplyNotice("Guardada en tu Pipeline. Cuando subas tu CV verás qué tanto encaja.");
    } catch (err) {
      setApplyError(err instanceof ApiError ? err.message : "No se pudo guardar.");
    } finally {
      setSavingToPipeline(false);
    }
  }

  async function handleChangeResumeLanguage(next: ProfileLanguage | null) {
    setResumeLanguage(next);
    // A CV already on screen is in the old language, and so is the reuse
    // suggestion — keeping either would quietly hand the user the wrong file.
    setResume(null);
    setReusable(null);
    try {
      const suggestion = await jobsApi.reusableResume(jobId, next ?? undefined);
      if (suggestion.resume_version) setReusable(suggestion);
    } catch {
      // Same as on load: the suggestion is a nice-to-have.
    }
  }

  async function handleGenerateResume() {
    setResumeLoading(true);
    setResumeError(null);
    try {
      const res = await jobsApi.generateResume(jobId, resumeLanguage ? { language: resumeLanguage } : undefined);
      setResume(res);
    } catch (err) {
      setResumeError(
        err instanceof ApiError ? err.message : "No se pudo generar un CV a medida."
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
        err instanceof ApiError ? err.message : "No se pudo generar la carta de presentación."
      );
    } finally {
      setCoverLoading(false);
    }
  }

  // Same reason as Pipeline and Home: the shape of what is coming, not a
  // spinner that collapses the layout and then shoves it back into place.
  if (loading) return <ListSkeleton rows={4} />;
  if (error) return <ErrorNotice message={error} onRetry={load} />;
  if (!job) return null;

  return (
    <div className="space-y-6 pb-4 animate-fade-in">
      <div className="rounded-2xl bg-white p-5 shadow-soft ring-1 ring-gray-100 dark:bg-gray-900 dark:ring-gray-800">
        <div className="flex items-start justify-between gap-3">
          <div className="flex min-w-0 flex-1 items-start gap-3">
            <span
              aria-hidden="true"
              className="mt-1 flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-brand-600 dark:bg-brand-200 dark:text-gray-950 font-display text-lg font-extrabold text-white shadow-brand"
            >
              {job.company?.trim()?.[0]?.toUpperCase() ?? "?"}
            </span>
            <div className="min-w-0">
              <h1 className="font-display text-[22px] font-extrabold leading-tight tracking-display-tight text-gray-900 dark:text-gray-50">
                {job.title}
              </h1>
              <p className="mt-0.5 text-sm text-gray-500 dark:text-gray-400">
                <span className="font-semibold text-gray-700 dark:text-gray-300">{job.company}</span>
                {job.location ? ` · ${job.location}` : ""}
                {job.deadline ? <DeadlineBadge deadline={job.deadline} className="ml-2 align-middle" /> : null}
                <ClosedBadge closedAt={job.closed_at} className="ml-2 align-middle" />
              </p>
              {job.work_auth && job.work_auth.blocks_you !== false && (
                <div className="mt-2">
                  <WorkAuthBadge workAuth={job.work_auth} />
                </div>
              )}
              {job.requires_cover_letter && (
                <span className="mt-2 inline-block rounded-full bg-accent-50 px-2.5 py-1 text-[10px] font-bold uppercase tracking-wide text-accent-700 ring-1 ring-inset ring-accent-600/20 dark:bg-accent-500/10 dark:text-accent-300 dark:ring-accent-400/30">
                  Requiere carta de presentación
                </span>
              )}
            </div>
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

        {/* Solo cuando la oferta publica un correo: es la única vía por la
            que JobPilot puede postular de verdad. Para el resto, el bloque de
            abajo sigue exactamente como estaba. */}
        {job.apply_email && !applied && (
          <div className="mt-4">
            <EmailApplyPanel
              jobId={job.id}
              applyEmail={job.apply_email}
              onSent={() => setApplied(true)}
            />
          </div>
        )}

        {noProfile && (
          <div className="mt-4 rounded-xl bg-amber-50 p-3 ring-1 ring-inset ring-amber-200 dark:bg-amber-500/10 dark:ring-amber-500/30">
            <p className="text-sm font-semibold text-amber-900 dark:text-amber-200">Primero sube tu CV</p>
            <p className="mt-1 text-xs leading-relaxed text-amber-800 dark:text-amber-300">
              Sin tu CV no podemos decirte qué tanto encajas ni prepararte el CV y la carta para esta
              vacante. Súbelo en PDF en Perfil (tarda un minuto) y vuelve aquí.
            </p>
            <div className="mt-2.5 flex flex-wrap gap-2">
              <Link href="/profile" className={buttonClass({ size: "sm" })}>
                Subir mi CV
              </Link>
              <Button variant="secondary" size="sm" onClick={handleSaveToPipeline} loading={savingToPipeline}>
                Guardar en Pipeline
              </Button>
            </div>
            {applyNotice && (
              <p className="mt-2 text-xs font-semibold text-emerald-700 dark:text-emerald-400">{applyNotice}</p>
            )}
            {applyError && <p className="mt-2 text-xs text-rose-600 dark:text-rose-400">{applyError}</p>}
          </div>
        )}

        <div className={`mt-4 rounded-xl bg-brand-50 p-3 dark:bg-brand-900/20 ${noProfile ? "hidden" : ""}`}>
          {/* Three steps instead of a six-line paragraph: this sits between
              the user and the button they came to press, and what it says is
              a sequence, not prose. */}
          {job.source_url ? (
            <ol className="space-y-1 text-xs font-medium text-brand-800 dark:text-brand-300">
              <li>1. Descarga tu CV en PDF, y lo genera si falta.</li>
              <li>
                2. Abre {job.apply_url ? "el formulario de la empresa" : "la vacante"} en otra pestaña
                para que subas ese PDF ahí.
              </li>
              <li>3. La registra en tu pipeline como aplicada.</li>
            </ol>
          ) : (
            <p className="text-xs font-medium text-brand-800 dark:text-brand-300">
              Esta vacante no trae link al sitio original: solo genero el CV y la carta, y registro la
              decisión en tu pipeline.
            </p>
          )}
          <p className="mt-2 text-[11px] leading-snug text-brand-700 dark:text-brand-400">
            {job.apply_email
              ? "O postula tú en el sitio original: el formulario ahí lo envías tú."
              : "Completar y mandar el formulario sigue siendo tuyo: JobPilot nunca lo envía por ti."}
          </p>
          {applyError && (
            <div className="mt-2">
              <ErrorNotice message={applyError} />
            </div>
          )}
          <button
            type="button"
            onClick={handleApply}
            disabled={applying || applied}
            className="mt-2 rounded-lg bg-brand-600 dark:bg-brand-200 dark:text-gray-950 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {applied ? "Aplicado ✓" : applying ? "Preparando…" : job.source_url ? "Aplicar" : "Marcar como aplicado"}
          </button>
          {applyNotice && !noProfile && (
            <p className="mt-1.5 text-xs font-semibold text-amber-700 dark:text-amber-400">{applyNotice}</p>
          )}
          {applied && (
            <p className="mt-1.5 text-xs text-brand-700 dark:text-brand-400">
              Registrado en tu pipeline con el CV descargado. Termina de completar el formulario en la
              pestaña que se abrió.
            </p>
          )}
        </div>
      </div>

      {/* Sits directly under the apply block on purpose: the moment the
          user taps "Aplicar" they're headed into someone else's form, and
          this is the panel they'll be tabbing back to. */}
      <ApplicationKit job={job} />

      {/* After the application kit: applying comes first, and the prep sheet
          is what you come back for once someone replies. */}
      <InterviewPrepCard jobId={job.id} />

      {/* Only when it adds something to the card the user already saw on
          Home: the same three bars a second time is a section that costs a
          scroll and answers nothing. Skills and concerns are the part that
          only exists here. */}
      {match &&
        (match.matched_skills.length > 0 ||
          match.missing_skills.length > 0 ||
          match.concerns.length > 0) && (
          <div className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-gray-100 dark:bg-gray-900 dark:ring-gray-800">
            <h2 className="mb-3 font-semibold text-gray-900 dark:text-gray-100">Desglose del match</h2>
            <MatchBreakdown match={match} />
          </div>
        )}

      <div className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-gray-100 dark:bg-gray-900 dark:ring-gray-800">
        <h2 className="mb-2 font-semibold text-gray-900 dark:text-gray-100">Descripción</h2>
        <CollapsibleText text={job.description} />
      </div>

      {job.requirements?.length > 0 && (
        <div className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-gray-100 dark:bg-gray-900 dark:ring-gray-800">
          <h2 className="mb-2 font-semibold text-gray-900 dark:text-gray-100">Requisitos</h2>
          <ul className="list-inside list-disc space-y-1 text-sm text-gray-700 dark:text-gray-300">
            {job.requirements.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </div>
      )}

      {job.responsibilities && job.responsibilities.length > 0 && (
        <div className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-gray-100 dark:bg-gray-900 dark:ring-gray-800">
          <h2 className="mb-2 font-semibold text-gray-900 dark:text-gray-100">Responsabilidades</h2>
          <ul className="list-inside list-disc space-y-1 text-sm text-gray-700 dark:text-gray-300">
            {job.responsibilities.map((r, i) => (
              <li key={i}>{r}</li>
            ))}
          </ul>
        </div>
      )}

      <div className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-gray-100 dark:bg-gray-900 dark:ring-gray-800">
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-semibold text-gray-900 dark:text-gray-100">CV a medida</h2>
          <div className="flex flex-wrap items-center gap-2">
            <select
              aria-label="Idioma del CV"
              value={resumeLanguage ?? "auto"}
              onChange={(e) =>
                handleChangeResumeLanguage(
                  e.target.value === "auto" ? null : (e.target.value as ProfileLanguage)
                )
              }
              className="rounded-lg border border-gray-200 bg-white px-2 py-1.5 text-xs font-semibold text-gray-600 outline-none focus:border-brand-500 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-300"
            >
              <option value="auto">Idioma de la vacante</option>
              <option value="en">English</option>
              <option value="es">Español</option>
            </select>
            <button
              type="button"
              onClick={handleGenerateResume}
              disabled={resumeLoading}
              className="rounded-lg bg-brand-600 dark:bg-brand-200 dark:text-gray-950 px-3 py-1.5 text-xs font-semibold text-white hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60"
            >
              {resumeLoading ? "Generando…" : resume ? "Regenerar" : "Generar CV"}
            </button>
          </div>
        </div>
        {resumeError && <ErrorNotice message={resumeError} />}
        {reusable?.resume_version && !resume && (
          <div className="mb-3 flex flex-col gap-3 rounded-xl border border-brand-100 bg-brand-50 p-3 text-sm sm:flex-row sm:items-center sm:justify-between dark:border-brand-900/40 dark:bg-brand-900/20">
            <p className="min-w-0 text-brand-800 dark:text-brand-300">
              Encontramos un CV ya adaptado para <strong>{reusable.source_job_title}</strong>
              {reusable.source_company ? ` @ ${reusable.source_company}` : ""} con{" "}
              {Math.round(reusable.similarity * 100)}% de requisitos en común — puedes reutilizarlo sin
              generar otro.
            </p>
            <button
              type="button"
              onClick={handleReuseResume}
              className="shrink-0 self-start rounded-lg bg-brand-600 dark:bg-brand-200 dark:text-gray-950 px-3 py-1.5 text-xs font-semibold text-white hover:bg-brand-700 sm:self-auto"
            >
              Reutilizar
            </button>
          </div>
        )}
        {resume && (
          <div className="mt-2 space-y-3 rounded-xl border border-gray-100 bg-gray-50 p-4 dark:border-gray-800 dark:bg-gray-800/50">
            <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
              {/* min-w-0 is what actually lets this column shrink: a flex
                  item defaults to min-width:auto, so a long unbreakable
                  title pushes the whole row wider than the card. */}
              <div className="min-w-0 flex-1">
                <div className="flex flex-wrap items-center gap-2">
                  <p className="break-words font-semibold text-gray-900 dark:text-gray-100">
                    {resume.title}
                  </p>
                  <span className="rounded-full bg-gray-200 px-2 py-0.5 text-[11px] font-semibold uppercase text-gray-600 dark:bg-gray-700 dark:text-gray-300">
                    {resume.language === "es" ? "Español" : "English"}
                  </span>
                </div>
                {resume.content.summary && (
                  <p className="mt-1 text-sm text-gray-600 dark:text-gray-400">{resume.content.summary}</p>
                )}
              </div>
              {/* No shrink-0: four buttons demanding their full width is
                  what squeezed the summary into a narrow ribbon on a phone.
                  They wrap under the text instead. */}
              <div className="flex flex-col gap-1.5 sm:items-end">
                <div className="flex flex-wrap gap-2 sm:justify-end">
                  <button
                    type="button"
                    onClick={() => setEditingResume((v) => !v)}
                    className="rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-semibold text-gray-600 hover:bg-gray-50 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800"
                  >
                    {editingResume ? "Ver" : "Editar"}
                  </button>
                  <button
                    type="button"
                    onClick={handleDownloadPdf}
                    disabled={pdfDownloading}
                    className="rounded-lg bg-brand-600 dark:bg-brand-200 dark:text-gray-950 px-3 py-1.5 text-xs font-semibold text-white hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60"
                  >
                    {pdfDownloading ? "Generando…" : "Descargar PDF"}
                  </button>
                  <button
                    type="button"
                    onClick={handleLatexExport}
                    disabled={overleafOpening}
                    title={
                      nativeApp
                        ? "Guarda el CV en LaTeX (.tex) para abrirlo en Overleaf desde una computadora"
                        : "Abre el CV en Overleaf como documento LaTeX, ya compilando"
                    }
                    className="rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-semibold text-gray-600 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800"
                  >
                    {overleafOpening
                      ? nativeApp
                        ? "Guardando…"
                        : "Abriendo…"
                      : nativeApp
                        ? "Guardar .tex"
                        : "LaTeX (Overleaf)"}
                  </button>
                  <CopyButton text={resumeToPlainText(resume)} />
                </div>
                {resume.edited_at && (
                  <span className="rounded-full bg-emerald-50 px-2 py-0.5 text-[10px] font-bold text-emerald-700 dark:bg-emerald-500/10 dark:text-emerald-300">
                    Editado por ti
                  </span>
                )}
                {pdfError && <p className="text-xs text-rose-600 dark:text-rose-400">{pdfError}</p>}
                {/* Antes de mandarlo, no despues: es el unico momento en que
                    este dato cambia lo que haces. */}
                <AtsCheckPanel resumeVersionId={resume.id} />
                {saveNotice && (
                  <p className="text-xs font-semibold text-emerald-700 dark:text-emerald-400">
                    {saveNotice}
                  </p>
                )}
              </div>
            </div>
            {resume.generated_by !== "ai" && !resume.edited_at && (
              <p className="text-[11px] text-amber-700 dark:text-amber-400">
                Hecho sin IA (no estaba disponible en este momento): revísalo antes de usarlo, o dale a
                Regenerar más tarde.
              </p>
            )}
            <p className="text-xs text-gray-400 dark:text-gray-400">
              El PDF usa formato de una columna con encabezados estándar (sin tablas ni imágenes) para que
              el &quot;autocompletar desde CV&quot; de la mayoría de formularios de aplicación lo lea bien.
            </p>

            {editingResume && (
              <ResumeEditor
                resume={resume}
                onSaved={(updated) => {
                  setResume(updated);
                  setEditingResume(false);
                }}
                onCancel={() => setEditingResume(false)}
              />
            )}

            {!editingResume && resume.content.skills.length > 0 && (
              <div>
                <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                  Habilidades
                </p>
                <div className="mt-1 flex flex-wrap gap-1.5">
                  {resume.content.skills.map((skill) => (
                    <SkillTag key={skill} label={skill} />
                  ))}
                </div>
              </div>
            )}

            {!editingResume && resume.content.experience.map((entry, i) => (
              <div key={i}>
                <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                  {entry.title} — {entry.company}
                </p>
                <ul className="mt-1 list-disc space-y-1 pl-5 text-sm leading-relaxed text-gray-700 dark:text-gray-300">
                  {entry.bullets.map((line, j) => (
                    <li key={j}>{line}</li>
                  ))}
                </ul>
              </div>
            ))}

            {resume.change_log.length > 0 && (
              <div className="border-t border-gray-200 pt-2 dark:border-gray-700">
                <p className="text-xs font-semibold uppercase tracking-wide text-gray-500 dark:text-gray-400">
                  Qué cambió
                </p>
                <ul className="mt-1 list-disc space-y-1 pl-5 text-xs text-gray-500 dark:text-gray-400">
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
        <div className="mb-3 flex flex-wrap items-center justify-between gap-2">
          <h2 className="font-semibold text-gray-900 dark:text-gray-100">Carta de presentación</h2>
          <button
            type="button"
            onClick={handleGenerateCoverLetter}
            disabled={coverLoading}
            className="rounded-lg bg-brand-600 dark:bg-brand-200 dark:text-gray-950 px-3 py-1.5 text-xs font-semibold text-white hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {coverLoading ? "Generando…" : coverLetter ? "Regenerar" : "Generar carta"}
          </button>
        </div>
        {coverError && <ErrorNotice message={coverError} />}
        {coverLetter && (
          <div className="mt-2 space-y-3 rounded-xl border border-gray-100 bg-gray-50 p-4 dark:border-gray-800 dark:bg-gray-800/50">
            <div className="flex flex-wrap justify-end gap-2">
              <button
                type="button"
                onClick={handleDownloadCoverLetterPdf}
                disabled={coverPdfDownloading}
                className="rounded-lg bg-brand-600 dark:bg-brand-200 dark:text-gray-950 px-3 py-1.5 text-xs font-semibold text-white hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60"
              >
                {coverPdfDownloading ? "Generando…" : "Descargar PDF"}
              </button>
              <CopyButton text={coverLetter.content} />
            </div>
            {coverPdfError && <p className="text-xs text-rose-600 dark:text-rose-400">{coverPdfError}</p>}
            {coverSaveNotice && (
              <p className="text-xs font-semibold text-emerald-700 dark:text-emerald-400">
                {coverSaveNotice}
              </p>
            )}
            {coverLetter.generated_by !== "ai" && (
              <p className="text-[11px] text-amber-700 dark:text-amber-400">
                Hecho sin IA (no estaba disponible en este momento): revísalo antes de usarlo, o dale a
                Regenerar más tarde.
              </p>
            )}
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
