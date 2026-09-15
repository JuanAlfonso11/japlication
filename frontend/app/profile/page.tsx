"use client";

import { useCallback, useEffect, useState } from "react";
import RouteGuard from "@/components/RouteGuard";
import { ListSkeleton } from "@/components/ui/Skeleton";
import ErrorNotice from "@/components/ErrorNotice";
import CVEvaluationCard from "@/components/CVEvaluationCard";
import SkillGapsCard from "@/components/SkillGapsCard";
import SegmentedTabs from "@/components/ui/SegmentedTabs";
import ErrorLogPanel from "@/components/ErrorLogPanel";
import { useAnnounce } from "@/components/LiveRegion";
import useUnsavedGuard from "@/components/useUnsavedGuard";
import SettingsPanel from "@/components/profile/SettingsPanel";
import UsedResumesSection from "@/components/profile/UsedResumesSection";
import SystemStatusPanel from "@/components/profile/SystemStatusPanel";
import { FormField, inputClass, textareaClass } from "@/components/ui/Field";
import SectionCard from "@/components/profile/SectionCard";
import SkillsSection from "@/components/profile/SkillsSection";
import ExperienceSection from "@/components/profile/ExperienceSection";
import EducationSection from "@/components/profile/EducationSection";
import CertificationsSection from "@/components/profile/CertificationsSection";
import LanguagesSection from "@/components/profile/LanguagesSection";
import ScreeningAnswersSection from "@/components/profile/ScreeningAnswersSection";
import MasterCvDownloads from "@/components/profile/MasterCvDownloads";
import { useAuth } from "@/context/AuthContext";
import { ApiError, jobsApi, profileApi } from "@/lib/api";
import {
  educationFor,
  experienceFor,
  headlineFor,
  setEducation,
  setExperience,
  setHeadline,
  setSummary,
  summaryFor,
} from "@/lib/profileLanguage";
import type {
  CareerProfile,
  CVEvaluation,
  LanguageStatus,
  ProfileLanguage,
} from "@/lib/types";

/** Normalizes a value for comparison: case, accents and punctuation removed,
 * whitespace collapsed. "Ingeniería de Software" and "ingenieria de software"
 * are the same entry typed twice. */
function normKey(...parts: (string | null | undefined)[]): string {
  return parts
    .map((p) => (p ?? "").toString().trim().toLowerCase())
    .join("|")
    .normalize("NFD")
    .replace(/[̀-ͯ]/g, "")
    .replace(/[^a-z0-9|]+/g, " ")
    .replace(/\s+/g, " ")
    .trim();
}

/** Appends only the entries of `incoming` that `current` does not already
 * have, judged by `keyOf`. */
function mergeUnique<T>(current: T[], incoming: T[], keyOf: (item: T) => string): T[] {
  const seen = new Set(current.map(keyOf));
  const added: T[] = [];
  for (const item of incoming) {
    const key = keyOf(item);
    if (key && seen.has(key)) continue;
    seen.add(key);
    added.push(item);
  }
  return [...current, ...added];
}

function mergeCvDraft(current: CareerProfile, draft: CareerProfile): CareerProfile {
  const mergedContact = { ...current.contact_info };
  (Object.keys(draft.contact_info) as (keyof typeof draft.contact_info)[]).forEach((key) => {
    if (!mergedContact[key] && draft.contact_info[key]) {
      mergedContact[key] = draft.contact_info[key];
    }
  });

  // Every list used to be a plain concatenation, so re-importing a corrected
  // PDF — the most natural thing to do when the first parse came out wrong —
  // left every job, degree and certification in the profile TWICE. Skills
  // were the only list that deduplicated. Cleaning eight duplicate entries by
  // hand on a phone is exactly the work the import was supposed to save, and
  // saving without noticing produced a duplicated CV.
  //
  // Identity per list is the field combination a person would call "the same
  // entry", not object equality — the parser rarely returns byte-identical
  // text twice.
  return {
    ...current,
    headline: current.headline || draft.headline || "",
    summary: current.summary || draft.summary || "",
    contact_info: mergedContact,
    skills: mergeUnique(current.skills, draft.skills, (s) => normKey(s.name)),
    experience: mergeUnique(current.experience, draft.experience, (e) =>
      normKey(e.company, e.title, e.start_date)
    ),
    education: mergeUnique(current.education, draft.education, (e) =>
      normKey(e.institution, e.degree, e.field)
    ),
    certifications: mergeUnique(current.certifications, draft.certifications, (c) =>
      normKey(typeof c === "string" ? c : c?.name)
    ),
    languages: mergeUnique(current.languages, draft.languages, (l) => normKey(l.name)),
  };
}

const EMPTY_PROFILE: CareerProfile = {
  headline: "",
  summary: "",
  contact_info: {
    phone: "",
    city: "",
    country: "",
    linkedin: "",
    github: "",
    portfolio: "",
  },
  skills: [],
  experience: [],
  education: [],
  certifications: [],
  languages: [],
  screening_answers: [],
  translations: {},
};

type ProfileTab = "cv" | "answers" | "insights" | "settings";

const TAB_STORAGE_KEY = "jobflow_profile_tab";
const CV_LANGUAGE_STORAGE_KEY = "jobflow_profile_cv_language";

function ProfileContent() {
  // Used for the master CV's filename: it is what a recruiter sees when the
  // file is attached to an application.
  const { user } = useAuth();
  const announce = useAnnounce();

  // Remembered across visits: coming back to Perfil to keep filling in the
  // answer bank and landing on the CV form every time is a small, repeated
  // annoyance. Read in an effect rather than in the initial state so the
  // server-rendered markup and the first client render agree.
  const [tab, setTab] = useState<ProfileTab>("cv");
  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(TAB_STORAGE_KEY);
      if (stored === "cv" || stored === "answers" || stored === "insights" || stored === "settings") {
        setTab(stored);
      }
    } catch {
      // localStorage unavailable (private mode) — the default tab is fine.
    }
  }, []);
  useEffect(() => {
    try {
      window.localStorage.setItem(TAB_STORAGE_KEY, tab);
    } catch {
      // Non-fatal: the choice just won't persist.
    }
  }, [tab]);

  const [profile, setProfile] = useState<CareerProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [lastSavedAt, setLastSavedAt] = useState<Date | null>(null);

  const [languages, setLanguages] = useState<LanguageStatus[] | null>(null);

  // Which language the CV form is editing. Remembered for the same reason
  // the tab is: someone filling in the Spanish version does it over several
  // visits, and landing back on English every time is a papercut.
  const [cvLanguage, setCvLanguage] = useState<ProfileLanguage>("es");
  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(CV_LANGUAGE_STORAGE_KEY);
      if (stored === "en" || stored === "es") setCvLanguage(stored);
    } catch {
      // localStorage unavailable (private mode) — the default is fine.
    }
  }, []);
  useEffect(() => {
    try {
      window.localStorage.setItem(CV_LANGUAGE_STORAGE_KEY, cvLanguage);
    } catch {
      // Non-fatal: the choice just won't persist.
    }
  }, [cvLanguage]);

  const [evaluation, setEvaluation] = useState<CVEvaluation | null>(null);
  const [evalLoading, setEvalLoading] = useState(false);
  const [evalError, setEvalError] = useState<string | null>(null);

  const [uploadingCv, setUploadingCv] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadNotice, setUploadNotice] = useState<{ warnings: string[]; generatedBy: string } | null>(null);
  const [cvImportedPendingSave, setCvImportedPendingSave] = useState(false);
  const [autoSearching, setAutoSearching] = useState(false);
  const [autoSearchNotice, setAutoSearchNotice] = useState<string | null>(null);

  const [improving, setImproving] = useState(false);
  const [improveError, setImproveError] = useState<string | null>(null);
  const [improveNotice, setImproveNotice] = useState<{
    changeLog: string[];
    generatedBy: string;
    scoreBefore: number | null;
    scoreAfter: number | null;
  } | null>(null);
  const [improvePendingSave, setImprovePendingSave] = useState(false);
  const [preImproveScore, setPreImproveScore] = useState<number | null>(null);

  const loadEvaluation = useCallback(async () => {
    setEvalLoading(true);
    setEvalError(null);
    try {
      const data = await profileApi.evaluation();
      setEvaluation(data);
    } catch (err) {
      // A profile that doesn't exist yet (404) just has nothing to evaluate —
      // not an error worth surfacing before the user has saved anything.
      if (err instanceof ApiError && err.status === 404) {
        setEvaluation(null);
      } else {
        setEvalError(err instanceof ApiError ? err.message : "No se pudo evaluar tu CV.");
      }
    } finally {
      setEvalLoading(false);
    }
  }, []);

  const loadLanguages = useCallback(async () => {
    try {
      setLanguages(await profileApi.languages());
    } catch {
      // Only drives a "faltan N campos" badge — never worth an error banner.
      setLanguages(null);
    }
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const data = await profileApi.get();
      // A profile saved before bilingual support has no `translations` key.
      setProfile({ ...data, translations: data.translations ?? {} });
      loadEvaluation();
      loadLanguages();
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setProfile(EMPTY_PROFILE);
      } else {
        setLoadError(
          err instanceof ApiError ? err.message : "No se pudo cargar tu perfil profesional."
        );
      }
    } finally {
      setLoading(false);
    }
  }, [loadEvaluation, loadLanguages]);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  // The bottom nav sits under the thumb on a phone; one reflex tap used to
  // discard everything typed since the last save, with no warning beyond a
  // small amber line at the top of the page.
  useUnsavedGuard(
    dirty,
    "Tienes cambios sin guardar en tu perfil. Si sales ahora se pierden.\n\n¿Salir de todas formas?"
  );

  function patch(update: Partial<CareerProfile>) {
    setProfile((prev) => (prev ? { ...prev, ...update } : prev));
    setDirty(true);
  }

  // Only the non-base language can be incomplete; English IS the profile.
  const esStatus = languages?.find((entry) => entry.code === "es") ?? null;

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    if (!profile) return;
    setSaving(true);
    setSaveError(null);
    try {
      const saved = await profileApi.save(profile);
      setProfile({ ...saved, translations: saved.translations ?? {} });
      setDirty(false);
      setLastSavedAt(new Date());
      // The "faltan N campos" badge is computed server-side, so it only
      // becomes true again after the save it is describing.
      loadLanguages();

      if (improvePendingSave) {
        setImprovePendingSave(false);
        try {
          const newEvaluation = await profileApi.evaluation();
          setEvaluation(newEvaluation);
          setImproveNotice((prev) =>
            prev ? { ...prev, scoreBefore: preImproveScore, scoreAfter: newEvaluation.overall_score } : prev
          );
        } catch {
          // Non-fatal — the improved profile still saved fine.
        }
      } else {
        loadEvaluation();
      }

      if (cvImportedPendingSave) {
        setCvImportedPendingSave(false);
        setAutoSearching(true);
        setAutoSearchNotice(null);
        try {
          const result = await jobsApi.autoImport();
          setAutoSearchNotice(
            result.imported > 0
              ? `Encontramos ${result.imported} vacante${result.imported === 1 ? "" : "s"} nueva${
                  result.imported === 1 ? "" : "s"
                } que hacen match — ya están en tu cola de Inicio.`
              : "Buscamos vacantes que hagan match con tu perfil, pero no encontramos nada nuevo por ahora. Prueba en Buscar más tarde."
          );
        } catch {
          // Non-fatal — the profile itself saved fine; the user can still
          // find jobs manually via Discover.
          setAutoSearchNotice(null);
        } finally {
          setAutoSearching(false);
        }
      }
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.message : "No se pudo guardar tu perfil.");
    } finally {
      setSaving(false);
    }
  }

  async function handleCvFileChange(e: React.ChangeEvent<HTMLInputElement>) {
    const file = e.target.files?.[0];
    e.target.value = ""; // allow re-uploading the same file again later
    if (!file) return;
    setUploadingCv(true);
    setUploadError(null);
    setUploadNotice(null);
    try {
      const result = await profileApi.importCv(file);
      setProfile((prev) => (prev ? mergeCvDraft(prev, result.profile) : prev));
      setDirty(true);
      setCvImportedPendingSave(true);
      setUploadNotice({ warnings: result.warnings, generatedBy: result.generated_by });
    } catch (err) {
      setUploadError(err instanceof ApiError ? err.message : "No se pudo leer ese PDF.");
    } finally {
      setUploadingCv(false);
    }
  }

  /** Snapshot of the user's own wording, taken right before "Mejorar CV"
   * overwrites it. The profile is described in the design as "the single
   * source of factual truth", and this button rewrites the headline, the
   * summary AND every achievement bullet in one shot. There was a text
   * change-log but no before/after and no way back: the only escape was to
   * leave without saving, which also threw away anything else edited in the
   * same session. A tool that scary is a tool you stop using. */
  const [preImproveProfile, setPreImproveProfile] = useState<Pick<
    CareerProfile,
    "headline" | "summary" | "experience"
  > | null>(null);

  function handleRevertImprove() {
    if (!preImproveProfile) return;
    patch(preImproveProfile);
    setPreImproveProfile(null);
    setImproveNotice(null);
    setImprovePendingSave(false);
    announce("Se restauró tu versión del CV.");
  }

  async function handleImproveProfile() {
    setImproving(true);
    setImproveError(null);
    setImproveNotice(null);
    setPreImproveScore(evaluation?.overall_score ?? null);
    try {
      const result = await profileApi.improve();
      if (profile) {
        setPreImproveProfile({
          headline: profile.headline,
          summary: profile.summary,
          experience: profile.experience,
        });
      }
      patch({
        headline: result.profile.headline,
        summary: result.profile.summary,
        experience: result.profile.experience,
      });
      setImprovePendingSave(true);
      setImproveNotice({
        changeLog: result.change_log,
        generatedBy: result.generated_by,
        scoreBefore: null,
        scoreAfter: null,
      });
    } catch (err) {
      setImproveError(err instanceof ApiError ? err.message : "No se pudo mejorar el CV.");
    } finally {
      setImproving(false);
    }
  }

  // A skeleton, not a centered spinner: globals.css says why — a spinner
  // reads as "stuck", and this screen takes 2.3-4.2s to load.
  if (loading) return <ListSkeleton rows={5} />;
  if (loadError) return <ErrorNotice message={loadError} onRetry={load} />;
  if (!profile) return null;

  return (
    <form onSubmit={handleSave} className="space-y-6 pb-4 animate-fade-in">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          {/* The tab is called "Perfil" and holds more than the CV (answers,
              analysis), so the screen it opens should say the same thing. */}
          <h1 className="font-display text-[26px] font-extrabold leading-tight tracking-display-tight text-gray-900 dark:text-gray-50">
            Perfil
          </h1>
          <p className="mt-1 max-w-[52ch] text-sm leading-relaxed text-gray-500 dark:text-gray-400">
            Mantén tu perfil actualizado — de aquí salen el match, los CVs a medida y las cartas de
            presentación.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span
            className={`text-xs font-medium ${
              dirty ? "text-amber-600 dark:text-amber-400" : "text-emerald-600 dark:text-emerald-400"
            }`}
          >
            {dirty
              ? "Cambios sin guardar"
              : lastSavedAt
              ? `Guardado ${lastSavedAt.toLocaleTimeString()}`
              : "Al día"}
          </span>
          {/* The second save button lived here: disabled most of the time,
              at the top of a form whose own save button sits at the end of
              it, where the thumb already is. The status text stays. */}
        </div>
      </div>

      <SegmentedTabs
        tabs={[
          { id: "cv", label: "Mi CV" },
          {
            id: "answers",
            label: "Respuestas",
            // Answered ones only: the badge is meant to show what's ready to
            // paste into a form, not how many blank prompts are sitting there.
            badge: (profile.screening_answers ?? []).filter((a) => a.answer.trim()).length,
          },
          { id: "insights", label: "Análisis" },
          // Ajustes was a floating gear that only appeared on Análisis, so
          // the account, the theme and "Cerrar sesión" lived somewhere the
          // user had no reason to look.
          { id: "settings", label: "Ajustes" },
        ]}
        value={tab}
        onChange={setTab}
      />

      {saveError && <ErrorNotice message={saveError} />}

      {autoSearching && (
        <div className="rounded-lg bg-brand-50 p-3 text-xs font-medium text-brand-700 ring-1 ring-inset ring-brand-600/20 dark:bg-brand-900/20 dark:text-brand-300 dark:ring-brand-400/30">
          Buscando vacantes que hagan match con tu nuevo perfil…
        </div>
      )}
      {!autoSearching && autoSearchNotice && (
        <div className="rounded-lg bg-emerald-50 p-3 text-xs font-medium text-emerald-800 ring-1 ring-inset ring-emerald-600/20 dark:bg-emerald-900/20 dark:text-emerald-300 dark:ring-emerald-400/30">
          {autoSearchNotice}
        </div>
      )}

      {tab === "cv" && (
      <div className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-gray-100 dark:bg-gray-900 dark:ring-gray-800">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">Importar desde un CV en PDF</p>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              Rellenamos los campos de abajo con tu PDF — nada se agrega a tu perfil guardado
              hasta que lo revises y le des a Guardar.
            </p>
          </div>
          <label className="shrink-0 cursor-pointer rounded-lg bg-brand-600 dark:bg-brand-200 dark:text-gray-950 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700 aria-disabled:cursor-not-allowed aria-disabled:opacity-60">
            {uploadingCv ? "Leyendo…" : "Subir PDF"}
            <input
              type="file"
              accept="application/pdf"
              className="hidden"
              disabled={uploadingCv}
              onChange={handleCvFileChange}
            />
          </label>
        </div>
        {uploadError && (
          <div className="mt-2">
            <ErrorNotice message={uploadError} />
          </div>
        )}
        {uploadNotice && (
          <div className="mt-3 rounded-lg bg-amber-50 p-3 text-xs text-amber-800 ring-1 ring-inset ring-amber-600/20 dark:bg-amber-900/20 dark:text-amber-300 dark:ring-amber-400/30">
            <p className="font-semibold">
              {uploadNotice.generatedBy === "ai"
                ? "Analizado con IA. Revisa los campos rellenados abajo y dale a Guardar."
                : "Analizado sin IA, con coincidencia básica de texto. Revisa con cuidado antes de guardar."}
            </p>
            {uploadNotice.warnings.map((w, i) => (
              <p key={i} className="mt-1">
                {w}
              </p>
            ))}
          </div>
        )}
      </div>
      )}

      {tab === "cv" && (
      <div className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-gray-100 dark:bg-gray-900 dark:ring-gray-800">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">Agente: mejorar CV principal</p>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              Reescribe tu titular, resumen y logros para que se lean mejor — mismos hechos, mejor
              redacción. No toca habilidades, educación ni certificaciones, y no afecta los CVs a medida
              que ya generaste para vacantes específicas. Nada se guarda hasta que revises y le des a
              Guardar perfil.
            </p>
          </div>
          <button
            type="button"
            onClick={handleImproveProfile}
            disabled={improving}
            className="shrink-0 rounded-lg bg-brand-600 dark:bg-brand-200 dark:text-gray-950 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {improving ? "Mejorando…" : "Mejorar CV"}
          </button>
        </div>
        {improveError && (
          <div className="mt-2">
            <ErrorNotice message={improveError} />
          </div>
        )}
        {improveNotice && (
          <div className="mt-3 rounded-lg bg-amber-50 p-3 text-xs text-amber-800 ring-1 ring-inset ring-amber-600/20 dark:bg-amber-900/20 dark:text-amber-300 dark:ring-amber-400/30">
            <p className="font-semibold">
              {improveNotice.generatedBy === "ai"
                ? "Reescrito con IA. Revisa los campos abajo (Resumen y Experiencia) y dale a Guardar perfil."
                : "Reescrito sin IA, con reglas básicas. Revisa antes de guardar."}
            </p>
            {improveNotice.changeLog.map((line, i) => (
              <p key={i} className="mt-1">
                {line}
              </p>
            ))}
            {improveNotice.scoreAfter != null && (
              <p className="mt-2 font-semibold">
                Puntaje del CV:{" "}
                {improveNotice.scoreBefore != null ? `${Math.round(improveNotice.scoreBefore)} → ` : ""}
                {Math.round(improveNotice.scoreAfter)}
                {improveNotice.scoreBefore != null &&
                  improveNotice.scoreAfter > improveNotice.scoreBefore &&
                  ` (+${Math.round(improveNotice.scoreAfter - improveNotice.scoreBefore)})`}
              </p>
            )}
            {preImproveProfile && (
              <div className="mt-3 border-t border-amber-600/20 pt-2.5 dark:border-amber-400/20">
                <p className="mb-2">
                  Tu versión anterior sigue guardada aquí hasta que salgas de esta pantalla.
                </p>
                <button
                  type="button"
                  onClick={handleRevertImprove}
                  className="min-h-[36px] rounded-lg bg-amber-100 px-3 text-xs font-bold text-amber-900 transition-colors hover:bg-amber-200 active:scale-95 dark:bg-amber-400/20 dark:text-amber-100 dark:hover:bg-amber-400/30"
                >
                  Restaurar mi versión
                </button>
              </div>
            )}
          </div>
        )}
      </div>
      )}

      {tab === "insights" && (
        <>
          <CVEvaluationCard evaluation={evaluation} loading={evalLoading} error={evalError} />

          {/* Right after the CV evaluation, which grades the profile in the
              abstract — this is the same question answered against the jobs
              the user actually wants, so the two belong together. */}
          <SkillGapsCard />

          <UsedResumesSection />
        </>
      )}

      {/* Análisis is about the CV; these three are about the machine running
          it. "Estado del sistema" talks about Task Scheduler and container
          watchdogs, and "Errores recientes" prints stack traces — between a
          CV health check and a list of skill gaps, they read as something
          the user did wrong. */}
      {tab === "settings" && (
        <>
          <SettingsPanel />

          <SystemStatusPanel />

          {/* Last: the thing you go looking for only when something already
              went wrong. */}
          <ErrorLogPanel />
        </>
      )}

      {tab === "cv" && (
        <div className="space-y-2">
          <SegmentedTabs
            tabs={[
              { id: "es", label: "Español" },
              { id: "en", label: "English" },
            ]}
            value={cvLanguage}
            onChange={setCvLanguage}
          />
          <p className="px-1 text-xs text-gray-500 dark:text-gray-400">
            {esStatus && !esStatus.complete && cvLanguage === "es"
              ? `Faltan ${esStatus.missing.length} campos por escribir en español — lo que dejes en blanco sale en inglés.`
              : "Habilidades, contacto, fechas y certificaciones son los mismos en ambos idiomas: lo que agregues en uno aparece en el otro."}
          </p>
          <MasterCvDownloads
            language={cvLanguage}
            fullName={user?.full_name}
            blockedReason={
              dirty
                ? "Guarda los cambios para descargar la versión actual."
                : !profile.id
                  ? "Guarda tu perfil para poder descargarlo."
                  : null
            }
          />
        </div>
      )}

      {tab === "cv" && (
      <SectionCard title="Resumen general" description="Cómo te ven los reclutadores de un vistazo.">
        <FormField label="Titular">
          <input
            className={inputClass}
            value={headlineFor(profile, cvLanguage)}
            onChange={(e) => patch(setHeadline(profile, cvLanguage, e.target.value))}
            placeholder={
              cvLanguage === "es" ? "Ingeniero Backend Senior" : "Senior Backend Engineer"
            }
          />
        </FormField>
        <FormField label="Resumen">
          <textarea
            className={textareaClass}
            value={summaryFor(profile, cvLanguage)}
            onChange={(e) => patch(setSummary(profile, cvLanguage, e.target.value))}
            placeholder={
              cvLanguage === "es"
                ? "Un breve resumen profesional…"
                : "A short professional summary…"
            }
          />
        </FormField>
      </SectionCard>
      )}

      {tab === "cv" && (
      <SectionCard title="Información de contacto">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <FormField label="Teléfono">
            <input
              className={inputClass}
              value={profile.contact_info.phone}
              onChange={(e) =>
                patch({ contact_info: { ...profile.contact_info, phone: e.target.value } })
              }
            />
          </FormField>
          <FormField label="Ciudad">
            <input
              className={inputClass}
              value={profile.contact_info.city}
              onChange={(e) =>
                patch({ contact_info: { ...profile.contact_info, city: e.target.value } })
              }
            />
          </FormField>
          <FormField label="País">
            <input
              className={inputClass}
              value={profile.contact_info.country}
              onChange={(e) =>
                patch({ contact_info: { ...profile.contact_info, country: e.target.value } })
              }
            />
          </FormField>
          <FormField label="LinkedIn">
            <input
              className={inputClass}
              value={profile.contact_info.linkedin}
              onChange={(e) =>
                patch({ contact_info: { ...profile.contact_info, linkedin: e.target.value } })
              }
            />
          </FormField>
          <FormField label="GitHub">
            <input
              className={inputClass}
              value={profile.contact_info.github}
              onChange={(e) =>
                patch({ contact_info: { ...profile.contact_info, github: e.target.value } })
              }
            />
          </FormField>
          <FormField label="Portafolio">
            <input
              className={inputClass}
              value={profile.contact_info.portfolio}
              onChange={(e) =>
                patch({ contact_info: { ...profile.contact_info, portfolio: e.target.value } })
              }
            />
          </FormField>
        </div>
      </SectionCard>
      )}

      {tab === "cv" && (
        <>
          {/* Shared across languages — a skill is the same fact in both, so
              there is only one copy and adding it here adds it everywhere. */}
          <SkillsSection skills={profile.skills} onChange={(skills) => patch({ skills })} />
          <ExperienceSection
            key={`exp-${cvLanguage}`}
            experience={experienceFor(profile, cvLanguage)}
            onChange={(experience) => patch(setExperience(profile, cvLanguage, experience))}
          />
          <EducationSection
            key={`edu-${cvLanguage}`}
            education={educationFor(profile, cvLanguage)}
            onChange={(education) => patch(setEducation(profile, cvLanguage, education))}
          />
          <CertificationsSection
            certifications={profile.certifications}
            onChange={(certifications) => patch({ certifications })}
          />
          <LanguagesSection
            languages={profile.languages}
            onChange={(languages) => patch({ languages })}
          />
        </>
      )}

      {tab === "answers" && (
        <ScreeningAnswersSection
          answers={profile.screening_answers ?? []}
          onChange={(screening_answers) => patch({ screening_answers })}
        />
      )}

      {/* Hidden on Análisis, which has nothing to save — but it stays
          mounted (and the form state with it), so edits made on another tab
          are never lost by switching. The header above still reports
          "Cambios sin guardar" from anywhere. */}
      {/* Only when there is something to save. It used to render always, so
          a pill reading "Guardado" floated over the last card's text and over
          the X that deletes a question. */}
      {tab !== "insights" && tab !== "settings" && (dirty || saving) && (
        <div className="sticky bottom-16 flex justify-end pb-2 md:bottom-0">
          <button
            type="submit"
            disabled={saving}
            className="rounded-full bg-brand-600 dark:bg-brand-200 dark:text-gray-950 px-5 py-3 text-sm font-semibold text-white shadow-lg hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {saving ? "Guardando…" : "Guardar cambios"}
          </button>
        </div>
      )}
    </form>
  );
}

export default function ProfilePage() {
  return (
    <RouteGuard>
      <ProfileContent />
    </RouteGuard>
  );
}
