"use client";

import { useMemo } from "react";
import SectionCard from "@/components/profile/SectionCard";
import { FormField, inputClass, textareaClass } from "@/components/ui/Field";
import type {
  CareerProfile,
  EducationTranslation,
  ExperienceTranslation,
  LanguageStatus,
  ProfileLanguage,
  ProfileTranslation,
} from "@/lib/types";

/**
 * Maintains the Spanish version of the profile.
 *
 * The layout is deliberately "base on top, translation below" for every
 * single field rather than a language switch that swaps the whole form.
 * A switch hides the thing you most need while translating — the original —
 * and makes it impossible to see at a glance what you have not done yet.
 * Here an empty box IS the to-do list.
 *
 * Only prose appears here. Dates, skills and contact details are the same
 * facts in both languages and live once, in the section above; showing them
 * twice is how the two copies quietly stop agreeing.
 */

const EMPTY_TRANSLATION: ProfileTranslation = {
  headline: "",
  summary: "",
  experience: [],
  education: [],
};

function emptyExperience(): ExperienceTranslation {
  return { title: "", company: "", location: "", bullets: [] };
}

/** The base text shown above each input. Muted and unselectable-looking on
 * purpose: it is context, not something you edit here. */
function BaseText({ children }: { children: string }) {
  if (!children) return null;
  return (
    <p className="mb-1.5 rounded-lg bg-gray-50 px-3 py-2 text-xs leading-relaxed text-gray-500 dark:bg-gray-800/50 dark:text-gray-400">
      {children}
    </p>
  );
}

/** Copies the base text verbatim — the right answer for anything that is
 * spelled the same in both languages (a company's registered name, a
 * product, a city). Saves retyping and, more importantly, stops the user
 * from "translating" a proper noun a recruiter searches for. */
function SameAsBase({ onClick, disabled }: { onClick: () => void; disabled: boolean }) {
  return (
    <button
      type="button"
      onClick={onClick}
      disabled={disabled}
      className="shrink-0 rounded-lg px-2 py-1 text-[11px] font-semibold text-brand-700 hover:bg-brand-50 disabled:cursor-not-allowed disabled:opacity-40 dark:text-brand-300 dark:hover:bg-brand-900/30"
    >
      = igual
    </button>
  );
}

export default function TranslationsSection({
  profile,
  language = "es",
  status,
  onChange,
}: {
  profile: CareerProfile;
  language?: ProfileLanguage;
  status?: LanguageStatus | null;
  onChange: (translations: CareerProfile["translations"]) => void;
}) {
  const translation = useMemo<ProfileTranslation>(
    () => ({ ...EMPTY_TRANSLATION, ...(profile.translations?.[language] ?? {}) }),
    [profile.translations, language]
  );

  function patch(changes: Partial<ProfileTranslation>) {
    onChange({ ...profile.translations, [language]: { ...translation, ...changes } });
  }

  function patchExperience(index: number, changes: Partial<ExperienceTranslation>) {
    // Padded to the base list's length so entry 2 can be translated before
    // entry 1 — positions are the only link between a translation and the
    // entry it belongs to, so a short array must never shift.
    const next = [...translation.experience];
    while (next.length <= index) next.push(emptyExperience());
    next[index] = { ...next[index], ...changes };
    patch({ experience: next });
  }

  function patchBullet(entryIndex: number, bulletIndex: number, value: string) {
    const current = translation.experience[entryIndex]?.bullets ?? [];
    const bullets = [...current];
    while (bullets.length <= bulletIndex) bullets.push("");
    bullets[bulletIndex] = value;
    patchExperience(entryIndex, { bullets });
  }

  function patchEducation(index: number, changes: Partial<EducationTranslation>) {
    const next = [...translation.education];
    while (next.length <= index) next.push({ degree: "", field: "", institution: "" });
    next[index] = { ...next[index], ...changes };
    patch({ education: next });
  }

  const pending = status && !status.complete ? status.missing.length : 0;

  return (
    <SectionCard
      title="Versión en español del CV"
      description="Tu perfil base está en inglés porque casi todas las vacantes lo están, y es el texto que el motor compara. Aquí mantienes el mismo CV en español."
    >
      <div className="flex flex-wrap items-center gap-2">
        {status && (
          <span
            className={`rounded-full px-2.5 py-1 text-[11px] font-semibold ${
              status.complete
                ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-900/30 dark:text-emerald-300"
                : "bg-amber-50 text-amber-700 dark:bg-amber-900/30 dark:text-amber-300"
            }`}
          >
            {status.complete ? "Completo" : `${pending} campo${pending === 1 ? "" : "s"} sin traducir`}
          </span>
        )}
        <span className="text-[11px] text-gray-500 dark:text-gray-400">
          Lo que dejes en blanco sale en inglés, nunca vacío.
        </span>
      </div>

      <FormField label="Titular">
        <BaseText>{profile.headline}</BaseText>
        <div className="flex items-start gap-1.5">
          <input
            className={inputClass}
            value={translation.headline ?? ""}
            onChange={(e) => patch({ headline: e.target.value })}
            placeholder="Ingeniero de Software Backend y Full-Stack"
          />
          <SameAsBase
            onClick={() => patch({ headline: profile.headline })}
            disabled={!profile.headline}
          />
        </div>
      </FormField>

      <FormField label="Resumen">
        <BaseText>{profile.summary}</BaseText>
        <textarea
          className={textareaClass}
          value={translation.summary ?? ""}
          onChange={(e) => patch({ summary: e.target.value })}
          placeholder="El mismo resumen, en español…"
        />
      </FormField>

      {profile.experience.map((entry, entryIndex) => {
        const translated = translation.experience[entryIndex] ?? emptyExperience();
        return (
          <div
            key={`exp-${entryIndex}`}
            className="rounded-xl border border-gray-200 p-4 dark:border-gray-700"
          >
            <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">
              Experiencia {entryIndex + 1}
            </p>

            <FormField label="Cargo">
              <BaseText>{entry.title}</BaseText>
              <div className="flex items-start gap-1.5">
                <input
                  className={inputClass}
                  value={translated.title ?? ""}
                  onChange={(e) => patchExperience(entryIndex, { title: e.target.value })}
                />
                <SameAsBase
                  onClick={() => patchExperience(entryIndex, { title: entry.title })}
                  disabled={!entry.title}
                />
              </div>
            </FormField>

            <FormField label="Empresa u organización" className="mt-3">
              <BaseText>{entry.company}</BaseText>
              <div className="flex items-start gap-1.5">
                <input
                  className={inputClass}
                  value={translated.company ?? ""}
                  onChange={(e) => patchExperience(entryIndex, { company: e.target.value })}
                  placeholder="Déjalo igual si es un nombre propio"
                />
                <SameAsBase
                  onClick={() => patchExperience(entryIndex, { company: entry.company })}
                  disabled={!entry.company}
                />
              </div>
            </FormField>

            {entry.bullets.length > 0 && (
              <div className="mt-3 space-y-3">
                <span className="block text-xs font-semibold text-gray-600 dark:text-gray-400">
                  Logros
                </span>
                {entry.bullets.map((bullet, bulletIndex) => (
                  <div key={`bullet-${entryIndex}-${bulletIndex}`}>
                    <BaseText>{bullet}</BaseText>
                    <textarea
                      className={textareaClass}
                      value={translated.bullets?.[bulletIndex] ?? ""}
                      onChange={(e) => patchBullet(entryIndex, bulletIndex, e.target.value)}
                    />
                  </div>
                ))}
              </div>
            )}
          </div>
        );
      })}

      {profile.education.map((entry, index) => {
        const translated = translation.education[index] ?? {};
        return (
          <div
            key={`edu-${index}`}
            className="rounded-xl border border-gray-200 p-4 dark:border-gray-700"
          >
            <p className="mb-3 text-xs font-semibold uppercase tracking-wide text-gray-400 dark:text-gray-500">
              Formación {index + 1}
            </p>

            <FormField label="Título">
              <BaseText>{entry.degree}</BaseText>
              <input
                className={inputClass}
                value={translated.degree ?? ""}
                onChange={(e) => patchEducation(index, { degree: e.target.value })}
              />
            </FormField>

            <FormField label="Área de estudio" className="mt-3">
              <BaseText>{entry.field}</BaseText>
              <input
                className={inputClass}
                value={translated.field ?? ""}
                onChange={(e) => patchEducation(index, { field: e.target.value })}
              />
            </FormField>
          </div>
        );
      })}

      {profile.experience.length === 0 && profile.education.length === 0 && (
        <p className="text-xs text-gray-500 dark:text-gray-400">
          Agrega experiencia o formación arriba y aquí aparecerán para traducirlas.
        </p>
      )}
    </SectionCard>
  );
}
