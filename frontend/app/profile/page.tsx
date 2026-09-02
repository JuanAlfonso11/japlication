"use client";

import { useCallback, useEffect, useState } from "react";
import RouteGuard from "@/components/RouteGuard";
import Spinner from "@/components/Spinner";
import ErrorNotice from "@/components/ErrorNotice";
import { FormField, inputClass, textareaClass } from "@/components/profile/FormField";
import SectionCard from "@/components/profile/SectionCard";
import SkillsSection from "@/components/profile/SkillsSection";
import ExperienceSection from "@/components/profile/ExperienceSection";
import EducationSection from "@/components/profile/EducationSection";
import CertificationsSection from "@/components/profile/CertificationsSection";
import LanguagesSection from "@/components/profile/LanguagesSection";
import { ApiError, profileApi } from "@/lib/api";
import type { CareerProfile } from "@/lib/types";

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

  const load = useCallback(async () => {
    setLoading(true);
    setLoadError(null);
    try {
      const data = await profileApi.get();
      setProfile(data);
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
  }, []);

  useEffect(() => {
    load();
  }, [load]);

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
    } catch (err) {
      setSaveError(err instanceof ApiError ? err.message : "Failed to save your profile.");
    } finally {
      setSaving(false);
    }
  }

  if (loading) return <Spinner label="Loading your profile…" />;
  if (loadError) return <ErrorNotice message={loadError} onRetry={load} />;
  if (!profile) return null;

  return (
    <form onSubmit={handleSave} className="space-y-6 pb-4 animate-fade-in">
      <div className="flex flex-wrap items-center justify-between gap-3">
        <div>
          <h1 className="text-2xl font-bold text-gray-900">CV Maestro</h1>
          <p className="mt-1 text-sm text-gray-500">
            Keep your career profile up to date — it powers matching, tailored resumes, and
            cover letters.
          </p>
        </div>
        <div className="flex items-center gap-3">
          <span
            className={`text-xs font-medium ${
              dirty ? "text-amber-600" : "text-emerald-600"
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
