"use client";

import { useCallback, useEffect, useState } from "react";
import RouteGuard from "@/components/RouteGuard";
import Spinner from "@/components/Spinner";
import ErrorNotice from "@/components/ErrorNotice";
import CVEvaluationCard from "@/components/CVEvaluationCard";
import { FormField, inputClass, textareaClass } from "@/components/profile/FormField";
import SectionCard from "@/components/profile/SectionCard";
import SkillsSection from "@/components/profile/SkillsSection";
import ExperienceSection from "@/components/profile/ExperienceSection";
import EducationSection from "@/components/profile/EducationSection";
import CertificationsSection from "@/components/profile/CertificationsSection";
import LanguagesSection from "@/components/profile/LanguagesSection";
import { ApiError, jobsApi, profileApi } from "@/lib/api";
import type { CareerProfile, CVEvaluation } from "@/lib/types";

function mergeCvDraft(current: CareerProfile, draft: CareerProfile): CareerProfile {
  const mergedContact = { ...current.contact_info };
  (Object.keys(draft.contact_info) as (keyof typeof draft.contact_info)[]).forEach((key) => {
    if (!mergedContact[key] && draft.contact_info[key]) {
      mergedContact[key] = draft.contact_info[key];
    }
  });

  const existingSkillNames = new Set(current.skills.map((s) => s.name.toLowerCase()));
  const newSkills = draft.skills.filter((s) => !existingSkillNames.has(s.name.toLowerCase()));

  return {
    ...current,
    headline: current.headline || draft.headline || "",
    summary: current.summary || draft.summary || "",
    contact_info: mergedContact,
    skills: [...current.skills, ...newSkills],
    experience: [...current.experience, ...draft.experience],
    education: [...current.education, ...draft.education],
    certifications: [...current.certifications, ...draft.certifications],
    languages: [...current.languages, ...draft.languages],
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
};

function ProfileContent() {
  const [profile, setProfile] = useState<CareerProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [saving, setSaving] = useState(false);
  const [saveError, setSaveError] = useState<string | null>(null);
  const [dirty, setDirty] = useState(false);
  const [lastSavedAt, setLastSavedAt] = useState<Date | null>(null);

  const [evaluation, setEvaluation] = useState<CVEvaluation | null>(null);
  const [evalLoading, setEvalLoading] = useState(false);
  const [evalError, setEvalError] = useState<string | null>(null);

  const [uploadingCv, setUploadingCv] = useState(false);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [uploadNotice, setUploadNotice] = useState<{ warnings: string[]; generatedBy: string } | null>(null);
  const [cvImportedPendingSave, setCvImportedPendingSave] = useState(false);
  const [autoSearching, setAutoSearching] = useState(false);
  const [autoSearchNotice, setAutoSearchNotice] = useState<string | null>(null);

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
        setEvalError(err instanceof ApiError ? err.message : "Could not evaluate your CV.");
      }
    } finally {
      setEvalLoading(false);
    }
  }, []);

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const data = await profileApi.get();
      setProfile(data);
      loadEvaluation();
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setProfile(EMPTY_PROFILE);
      } else {
        setLoadError(
          err instanceof ApiError ? err.message : "Failed to load your career profile."
        );
      }
    } finally {
      setLoading(false);
    }
  }, [loadEvaluation]);

  useEffect(() => {
    load();
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  function patch(update: Partial<CareerProfile>) {
    setProfile((prev) => (prev ? { ...prev, ...update } : prev));
    setDirty(true);
  }

  async function handleSave(e: React.FormEvent) {
    e.preventDefault();
    if (!profile) return;
    setSaving(true);
    setSaveError(null);
    try {
      const saved = await profileApi.save(profile);
      setProfile(saved);
      setDirty(false);
      setLastSavedAt(new Date());
      loadEvaluation();

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
              : "Buscamos vacantes que hagan match con tu perfil, pero no encontramos nada nuevo por ahora — prueba Discover más tarde."
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
      setSaveError(err instanceof ApiError ? err.message : "Failed to save your profile.");
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
      setUploadError(err instanceof ApiError ? err.message : "Could not read that PDF.");
    } finally {
      setUploadingCv(false);
    }
  }

  if (loading) return <Spinner label="Loading your profile…" />;
  if (loadError) return <ErrorNotice message={loadError} onRetry={load} />;
  if (!profile) return null;

  return (
    <form onSubmit={handleSave} className="space-y-6 pb-4 animate-fade-in">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">CV Maestro</h1>
          <p className="mt-1 text-sm text-gray-500 dark:text-gray-400">
            Keep your career profile up to date — it powers matching, tailored resumes, and
            cover letters.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span
            className={`text-xs font-medium ${
              dirty ? "text-amber-600 dark:text-amber-400" : "text-emerald-600 dark:text-emerald-400"
            }`}
          >
            {dirty
              ? "Unsaved changes"
              : lastSavedAt
              ? `Saved ${lastSavedAt.toLocaleTimeString()}`
              : "Up to date"}
          </span>
          <button
            type="submit"
            disabled={saving || !dirty}
            className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
          >
            {saving ? "Saving…" : "Save profile"}
          </button>
        </div>
      </div>

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

      <div className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-gray-100 dark:bg-gray-900 dark:ring-gray-800">
        <div className="flex flex-wrap items-center justify-between gap-3">
          <div>
            <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">Import from a PDF résumé</p>
            <p className="text-xs text-gray-500 dark:text-gray-400">
              We pre-fill the fields below from your PDF — nothing is added to your saved profile
              until you review it and click Save.
            </p>
          </div>
          <label className="shrink-0 cursor-pointer rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700 aria-disabled:cursor-not-allowed aria-disabled:opacity-60">
            {uploadingCv ? "Reading…" : "Upload PDF"}
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
                ? "Parsed with AI — review the pre-filled fields below and click Save."
                : "Parsed with basic text matching (no ANTHROPIC_API_KEY configured) — review carefully before saving."}
            </p>
            {uploadNotice.warnings.map((w, i) => (
              <p key={i} className="mt-1">
                {w}
              </p>
            ))}
          </div>
        )}
      </div>

      <CVEvaluationCard evaluation={evaluation} loading={evalLoading} error={evalError} />

      <SectionCard title="Overview" description="How recruiters see you at a glance.">
        <FormField label="Headline">
          <input
            className={inputClass}
            value={profile.headline}
            onChange={(e) => patch({ headline: e.target.value })}
            placeholder="Senior Backend Engineer"
          />
        </FormField>
        <FormField label="Summary">
          <textarea
            className={textareaClass}
            value={profile.summary}
            onChange={(e) => patch({ summary: e.target.value })}
            placeholder="A short professional summary…"
          />
        </FormField>
      </SectionCard>

      <SectionCard title="Contact info">
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
          <FormField label="Phone">
            <input
              className={inputClass}
              value={profile.contact_info.phone}
              onChange={(e) =>
                patch({ contact_info: { ...profile.contact_info, phone: e.target.value } })
              }
            />
          </FormField>
          <FormField label="City">
            <input
              className={inputClass}
              value={profile.contact_info.city}
              onChange={(e) =>
                patch({ contact_info: { ...profile.contact_info, city: e.target.value } })
              }
            />
          </FormField>
          <FormField label="Country">
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
          <FormField label="Portfolio">
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

      <SkillsSection skills={profile.skills} onChange={(skills) => patch({ skills })} />
      <ExperienceSection
        experience={profile.experience}
        onChange={(experience) => patch({ experience })}
      />
      <EducationSection
        education={profile.education}
        onChange={(education) => patch({ education })}
      />
      <CertificationsSection
        certifications={profile.certifications}
        onChange={(certifications) => patch({ certifications })}
      />
      <LanguagesSection
        languages={profile.languages}
        onChange={(languages) => patch({ languages })}
      />

      <div className="sticky bottom-16 flex justify-end md:bottom-0">
        <button
          type="submit"
          disabled={saving || !dirty}
          className="rounded-full bg-brand-600 px-5 py-3 text-sm font-semibold text-white shadow-lg hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-50"
        >
          {saving ? "Saving…" : dirty ? "Save changes" : "Saved"}
        </button>
      </div>
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
