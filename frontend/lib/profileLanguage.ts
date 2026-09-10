import {
  BASE_PROFILE_LANGUAGE,
  type CareerProfile,
  type EducationEntry,
  type EducationTranslation,
  type ExperienceEntry,
  type ExperienceTranslation,
  type ProfileLanguage,
  type ProfileTranslation,
} from "@/lib/types";

/**
 * Lets the profile form edit ONE language at a time while the profile stays
 * a single record.
 *
 * The split is not cosmetic. A career profile is two different kinds of
 * data wearing the same shape:
 *
 *   facts  — dates, skills, contact details, which technologies a role used.
 *            The same in every language. Stored once. Editing them in the
 *            Spanish view edits the only copy there is, which is why adding
 *            a skill "in Spanish" makes it appear in English too: there was
 *            never a second copy to keep in sync.
 *
 *   prose  — headline, summary, job titles, organization names, bullets,
 *            degree names. These genuinely differ per language and live in
 *            `translations`, keyed by language code.
 *
 * The `xFor` readers merge the two into the shape the existing form
 * components already accept, and the `setX` writers split an edited view
 * back apart. The form components never learn that languages exist.
 *
 * Every prose field is named explicitly rather than looped over a list of
 * keys. A dynamic lookup needs a cast through `unknown` at each end, and a
 * cast is exactly what would stop the compiler from noticing when a new
 * field is added to one side and forgotten on the other.
 */

const EMPTY_TRANSLATION: ProfileTranslation = {
  headline: "",
  summary: "",
  experience: [],
  education: [],
};

function translationFor(profile: CareerProfile, language: ProfileLanguage): ProfileTranslation {
  return { ...EMPTY_TRANSLATION, ...(profile.translations?.[language] ?? {}) };
}

function hasText(value: string | string[] | null | undefined): boolean {
  if (Array.isArray(value)) return value.some((item) => item.trim().length > 0);
  return typeof value === "string" && value.trim().length > 0;
}

/** Prose the reader should see: the translation when it has content, the
 * base otherwise. A blank translation means "not written yet", never "this
 * person has no summary" — the CV renderer does the same thing server-side
 * (see backend/app/services/profile_i18n.py). */
function preferredText(override: string | undefined, base: string): string {
  return hasText(override) ? (override as string) : base;
}

function preferredList(override: string[] | undefined, base: string[]): string[] {
  return hasText(override) ? (override as string[]) : base;
}

// --- Reading -------------------------------------------------------------

export function headlineFor(profile: CareerProfile, language: ProfileLanguage): string {
  if (language === BASE_PROFILE_LANGUAGE) return profile.headline;
  return preferredText(translationFor(profile, language).headline, profile.headline);
}

export function summaryFor(profile: CareerProfile, language: ProfileLanguage): string {
  if (language === BASE_PROFILE_LANGUAGE) return profile.summary;
  return preferredText(translationFor(profile, language).summary, profile.summary);
}

export function experienceFor(
  profile: CareerProfile,
  language: ProfileLanguage
): ExperienceEntry[] {
  if (language === BASE_PROFILE_LANGUAGE) return profile.experience;
  const overrides = translationFor(profile, language).experience ?? [];
  return profile.experience.map((entry, index) => {
    const override = overrides[index];
    if (!override) return entry;
    return {
      ...entry,
      title: preferredText(override.title, entry.title),
      company: preferredText(override.company, entry.company),
      location: preferredText(override.location, entry.location),
      bullets: preferredList(override.bullets, entry.bullets),
    };
  });
}

export function educationFor(profile: CareerProfile, language: ProfileLanguage): EducationEntry[] {
  if (language === BASE_PROFILE_LANGUAGE) return profile.education;
  const overrides = translationFor(profile, language).education ?? [];
  return profile.education.map((entry, index) => {
    const override = overrides[index];
    if (!override) return entry;
    return {
      ...entry,
      degree: preferredText(override.degree, entry.degree),
      field: preferredText(override.field, entry.field),
      institution: preferredText(override.institution, entry.institution),
    };
  });
}

// --- Writing -------------------------------------------------------------

/** Whether a piece of prose typed in one language should also seed the
 * other.
 *
 * Writing in a non-base language normally only touches the translation. The
 * exception is a base that is still empty: typing the first version of a
 * bullet in Spanish must not leave the English CV with a hole in it, so the
 * text seeds both. Once the base has content the two are independent and
 * editing one never rewrites the other. */
function seedsBase(baseValue: string | string[] | null | undefined): boolean {
  return !hasText(baseValue);
}

export function setHeadline(
  profile: CareerProfile,
  language: ProfileLanguage,
  value: string
): Partial<CareerProfile> {
  if (language === BASE_PROFILE_LANGUAGE) return { headline: value };
  const translation = { ...translationFor(profile, language), headline: value };
  const update: Partial<CareerProfile> = {
    translations: { ...profile.translations, [language]: translation },
  };
  if (seedsBase(profile.headline)) update.headline = value;
  return update;
}

export function setSummary(
  profile: CareerProfile,
  language: ProfileLanguage,
  value: string
): Partial<CareerProfile> {
  if (language === BASE_PROFILE_LANGUAGE) return { summary: value };
  const translation = { ...translationFor(profile, language), summary: value };
  const update: Partial<CareerProfile> = {
    translations: { ...profile.translations, [language]: translation },
  };
  if (seedsBase(profile.summary)) update.summary = value;
  return update;
}

/** Splits an edited experience list back into shared facts and per-language
 * prose. Handles rows being added and removed, which is the case a naive
 * "just write the prose to the translation" approach gets wrong: the two
 * lists are matched by position, so a row removed from one must be removed
 * from the other or every later translation shifts onto the wrong job. */
export function setExperience(
  profile: CareerProfile,
  language: ProfileLanguage,
  next: ExperienceEntry[]
): Partial<CareerProfile> {
  if (language === BASE_PROFILE_LANGUAGE) {
    return {
      experience: next,
      translations: realignExperience(profile, profile.experience, next),
    };
  }

  const mapping = matchRows(experienceFor(profile, language), next);
  const translation = translationFor(profile, language);

  const base: ExperienceEntry[] = [];
  const overrides: ExperienceTranslation[] = [];

  next.forEach((row, index) => {
    const source = mapping[index];
    const baseRow: ExperienceEntry =
      source === null ? { ...row, bullets: [...row.bullets] } : { ...profile.experience[source] };
    const prior: ExperienceTranslation =
      source === null ? { bullets: [] } : (translation.experience?.[source] ?? { bullets: [] });

    // Facts land on the base row — there is only one copy of them.
    baseRow.start_date = row.start_date;
    baseRow.end_date = row.end_date;
    baseRow.skills_used = row.skills_used;

    if (seedsBase(baseRow.title)) baseRow.title = row.title;
    if (seedsBase(baseRow.company)) baseRow.company = row.company;
    if (seedsBase(baseRow.location)) baseRow.location = row.location;
    if (seedsBase(baseRow.bullets)) baseRow.bullets = [...row.bullets];

    base.push(baseRow);
    overrides.push({
      ...prior,
      title: row.title,
      company: row.company,
      location: row.location,
      bullets: [...row.bullets],
    });
  });

  return {
    experience: base,
    translations: {
      ...profile.translations,
      [language]: { ...translation, experience: overrides },
    },
  };
}

export function setEducation(
  profile: CareerProfile,
  language: ProfileLanguage,
  next: EducationEntry[]
): Partial<CareerProfile> {
  if (language === BASE_PROFILE_LANGUAGE) {
    return {
      education: next,
      translations: realignEducation(profile, profile.education, next),
    };
  }

  const mapping = matchRows(educationFor(profile, language), next);
  const translation = translationFor(profile, language);

  const base: EducationEntry[] = [];
  const overrides: EducationTranslation[] = [];

  next.forEach((row, index) => {
    const source = mapping[index];
    const baseRow: EducationEntry = source === null ? { ...row } : { ...profile.education[source] };
    const prior: EducationTranslation =
      source === null ? {} : { ...(translation.education?.[source] ?? {}) };

    baseRow.start_date = row.start_date;
    baseRow.end_date = row.end_date;

    if (seedsBase(baseRow.degree)) baseRow.degree = row.degree;
    if (seedsBase(baseRow.field)) baseRow.field = row.field;
    if (seedsBase(baseRow.institution)) baseRow.institution = row.institution;

    base.push(baseRow);
    overrides.push({
      ...prior,
      degree: row.degree,
      field: row.field,
      institution: row.institution,
    });
  });

  return {
    education: base,
    translations: {
      ...profile.translations,
      [language]: { ...translation, education: overrides },
    },
  };
}

// --- Keeping the two lists aligned ---------------------------------------

/** Maps each row of the edited list back to its index in the list it was
 * derived from, or null for a row that was just added.
 *
 * Object identity would be the obvious way to do this and does NOT work:
 * the readers above rebuild a row whenever it has a translation, so the
 * array they return has fresh objects every call and nothing the form hands
 * back is ever `===` to anything we can recompute.
 *
 * What does hold is that one onChange is one user action. The form
 * components edit in place, append to the end, or filter one row out — they
 * never do two of those at once. So:
 *
 *   same length or longer  -> rows kept their positions; the extras are new
 *   shorter                -> rows were removed and nothing was edited,
 *                             which makes value equality exact
 *
 * The two-pointer walk below handles the removal case, including more than
 * one row disappearing at a time. */
export function matchRows<T>(previous: T[], next: T[]): (number | null)[] {
  if (next.length >= previous.length) {
    return next.map((_, index) => (index < previous.length ? index : null));
  }

  const signature = (row: T) => JSON.stringify(row);
  const mapping: (number | null)[] = [];
  let cursor = 0;

  for (const row of next) {
    const target = signature(row);
    let found: number | null = null;
    for (let i = cursor; i < previous.length; i += 1) {
      if (signature(previous[i]) === target) {
        found = i;
        cursor = i + 1;
        break;
      }
    }
    // No match means the assumption above did not hold (an edit and a
    // removal in one go). Positional is the least surprising fallback: it
    // keeps the surviving rows lined up instead of dropping translations.
    mapping.push(found ?? (mapping.length < previous.length ? mapping.length : null));
  }

  return mapping;
}

/** When the BASE list is edited, every translation has to follow the same
 * add/remove/reorder or its rows drift onto the wrong entries. */
function realignExperience(
  profile: CareerProfile,
  previous: ExperienceEntry[],
  next: ExperienceEntry[]
): CareerProfile["translations"] {
  const mapping = matchRows(previous, next);
  const out: CareerProfile["translations"] = {};
  const translations = profile.translations ?? {};

  (Object.keys(translations) as ProfileLanguage[]).forEach((language) => {
    const translation = translations[language];
    if (!translation) return;
    const rows = translation.experience ?? [];
    out[language] = {
      ...translation,
      experience: mapping.map((source) =>
        source === null ? { bullets: [] } : (rows[source] ?? { bullets: [] })
      ),
    };
  });

  return out;
}

function realignEducation(
  profile: CareerProfile,
  previous: EducationEntry[],
  next: EducationEntry[]
): CareerProfile["translations"] {
  const mapping = matchRows(previous, next);
  const out: CareerProfile["translations"] = {};
  const translations = profile.translations ?? {};

  (Object.keys(translations) as ProfileLanguage[]).forEach((language) => {
    const translation = translations[language];
    if (!translation) return;
    const rows = translation.education ?? [];
    out[language] = {
      ...translation,
      education: mapping.map((source) => (source === null ? {} : (rows[source] ?? {}))),
    };
  });

  return out;
}
