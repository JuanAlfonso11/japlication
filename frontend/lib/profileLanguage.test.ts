import { describe, expect, it } from "vitest";
import {
  educationFor,
  experienceFor,
  headlineFor,
  setEducation,
  setExperience,
  setHeadline,
  setSummary,
  summaryFor,
} from "./profileLanguage";
import type { CareerProfile } from "./types";

/**
 * The failure mode these guard against is silent and expensive: a CV that
 * looks fine on screen but has the wrong dates on a job, a bullet attached
 * to the employer it did not happen at, or an English section that emptied
 * out because it was edited while the form was in Spanish.
 *
 * Nothing here checks wording. It all checks that facts stay shared, prose
 * stays separate, and the two lists stay lined up.
 */

function profile(overrides: Partial<CareerProfile> = {}): CareerProfile {
  return {
    headline: "Backend Engineer",
    summary: "Engineer with C# experience.",
    contact_info: {
      phone: "",
      city: "Santiago",
      country: "RD",
      linkedin: "",
      github: "",
      portfolio: "",
    },
    skills: [{ name: "C#", category: "language", level: "advanced", years_experience: 3 }],
    experience: [
      {
        company: "PUCMM",
        title: "Software Developer",
        start_date: "2021-01",
        end_date: null,
        location: "Santiago",
        bullets: ["Built mobile apps with Xamarin."],
        skills_used: ["C#"],
      },
    ],
    education: [
      {
        institution: "PUCMM",
        degree: "Bachelor's Degree",
        field: "Computer Science",
        start_date: "2018",
        end_date: "2023",
      },
    ],
    certifications: [],
    languages: [],
    screening_answers: [],
    translations: {
      es: {
        headline: "Ingeniero Backend",
        summary: "Ingeniero con experiencia en C#.",
        experience: [
          { title: "Desarrollador de Software", bullets: ["Construí apps móviles con Xamarin."] },
        ],
        education: [{ degree: "Licenciatura", field: "Ciencias de la Computación" }],
      },
    },
    ...overrides,
  };
}

describe("reading a language", () => {
  it("shows each language its own prose", () => {
    const p = profile();
    expect(headlineFor(p, "en")).toBe("Backend Engineer");
    expect(headlineFor(p, "es")).toBe("Ingeniero Backend");
    expect(summaryFor(p, "es")).toBe("Ingeniero con experiencia en C#.");
    expect(experienceFor(p, "es")[0].title).toBe("Desarrollador de Software");
    expect(educationFor(p, "es")[0].degree).toBe("Licenciatura");
  });

  it("shows the same facts to both languages", () => {
    const p = profile();
    const en = experienceFor(p, "en")[0];
    const es = experienceFor(p, "es")[0];
    expect(es.start_date).toBe(en.start_date);
    expect(es.end_date).toBe(en.end_date);
    expect(es.skills_used).toEqual(en.skills_used);
  });

  it("falls back to the base for prose that has no translation yet", () => {
    // Company was never translated; the Spanish view must show the English
    // one rather than an empty field.
    expect(experienceFor(profile(), "es")[0].company).toBe("PUCMM");
    expect(educationFor(profile(), "es")[0].institution).toBe("PUCMM");
  });

  it("treats a blank translation as 'not written yet', not as a deletion", () => {
    const p = profile({
      translations: { es: { headline: "   ", summary: "", experience: [], education: [] } },
    });
    expect(headlineFor(p, "es")).toBe("Backend Engineer");
    expect(summaryFor(p, "es")).toBe("Engineer with C# experience.");
  });
});

describe("writing in Spanish", () => {
  it("does not touch the English prose", () => {
    const p = profile();
    const update = setHeadline(p, "es", "Ingeniero de Software");
    expect(update.headline).toBeUndefined();
    expect(update.translations?.es?.headline).toBe("Ingeniero de Software");
  });

  it("writes shared facts to the one copy that exists", () => {
    const p = profile();
    const edited = experienceFor(p, "es").map((entry) => ({
      ...entry,
      end_date: "2024-06",
      skills_used: ["C#", "AWS"],
    }));
    const update = setExperience(p, "es", edited);

    // The fact landed on the base row, so English sees it too.
    expect(update.experience?.[0].end_date).toBe("2024-06");
    expect(update.experience?.[0].skills_used).toEqual(["C#", "AWS"]);
    // ...and the English prose is untouched.
    expect(update.experience?.[0].title).toBe("Software Developer");
    expect(update.translations?.es?.experience?.[0].title).toBe("Desarrollador de Software");
  });

  it("seeds the base when it is still empty, so no CV ends up with a hole", () => {
    const p = profile({ headline: "", summary: "" });
    expect(setHeadline(p, "es", "Ingeniero Backend").headline).toBe("Ingeniero Backend");
    expect(setSummary(p, "es", "Un resumen.").summary).toBe("Un resumen.");
  });

  it("stops seeding once the base has its own text", () => {
    const p = profile();
    expect(setHeadline(p, "es", "Otro titular").headline).toBeUndefined();
  });
});

describe("adding and removing rows", () => {
  it("keeps a new role's text in both languages", () => {
    const p = profile();
    const edited = [
      ...experienceFor(p, "es"),
      {
        company: "Nueva Empresa",
        title: "Desarrollador",
        start_date: "2024-01",
        end_date: null,
        location: "Remoto",
        bullets: ["Hice cosas."],
        skills_used: [],
      },
    ];
    const update = setExperience(p, "es", edited);

    expect(update.experience).toHaveLength(2);
    expect(update.translations?.es?.experience).toHaveLength(2);
    // Typed in Spanish with no English yet: the English CV shows the
    // Spanish text rather than a blank role.
    expect(update.experience?.[1].title).toBe("Desarrollador");
    expect(update.translations?.es?.experience?.[1].title).toBe("Desarrollador");
    // The first role's translation did not shift onto the new one.
    expect(update.translations?.es?.experience?.[0].title).toBe("Desarrollador de Software");
  });

  it("removes the translation of a removed role instead of shifting it", () => {
    // Two roles with clearly different translations: if removal shifted the
    // list, role 2 would inherit role 1's Spanish text and nothing on screen
    // would look wrong.
    const p = profile({
      experience: [
        { company: "A", title: "First", start_date: "2020", end_date: null, location: "", bullets: ["a"], skills_used: [] },
        { company: "B", title: "Second", start_date: "2022", end_date: null, location: "", bullets: ["b"], skills_used: [] },
      ],
      translations: {
        es: {
          headline: "",
          summary: "",
          experience: [
            { title: "Primero", bullets: ["uno"] },
            { title: "Segundo", bullets: ["dos"] },
          ],
          education: [],
        },
      },
    });

    const view = experienceFor(p, "es");
    const update = setExperience(p, "es", view.slice(1)); // drop the first

    expect(update.experience).toHaveLength(1);
    expect(update.experience?.[0].company).toBe("B");
    expect(update.translations?.es?.experience?.[0].title).toBe("Segundo");
  });

  it("realigns translations when a row is removed from the ENGLISH view", () => {
    const p = profile({
      experience: [
        { company: "A", title: "First", start_date: "2020", end_date: null, location: "", bullets: ["a"], skills_used: [] },
        { company: "B", title: "Second", start_date: "2022", end_date: null, location: "", bullets: ["b"], skills_used: [] },
      ],
      translations: {
        es: {
          headline: "",
          summary: "",
          experience: [
            { title: "Primero", bullets: ["uno"] },
            { title: "Segundo", bullets: ["dos"] },
          ],
          education: [],
        },
      },
    });

    const update = setExperience(p, "en", p.experience.slice(1));

    expect(update.experience?.[0].company).toBe("B");
    expect(update.translations?.es?.experience).toHaveLength(1);
    expect(update.translations?.es?.experience?.[0].title).toBe("Segundo");
  });

  it("survives removing two roles at once", () => {
    const rol = (n: string) => ({
      company: n,
      title: `Title ${n}`,
      start_date: "2020",
      end_date: null,
      location: "",
      bullets: [`bullet ${n}`],
      skills_used: [],
    });
    const p = profile({
      experience: [rol("A"), rol("B"), rol("C")],
      translations: {
        es: {
          headline: "",
          summary: "",
          experience: [
            { title: "Uno", bullets: ["uno"] },
            { title: "Dos", bullets: ["dos"] },
            { title: "Tres", bullets: ["tres"] },
          ],
          education: [],
        },
      },
    });

    const view = experienceFor(p, "es");
    const update = setExperience(p, "es", [view[0], view[2]]);

    expect(update.experience?.map((e) => e.company)).toEqual(["A", "C"]);
    expect(update.translations?.es?.experience?.map((e) => e.title)).toEqual(["Uno", "Tres"]);
  });

  it("keeps education aligned the same way", () => {
    const p = profile();
    const edited = educationFor(p, "es").map((entry) => ({ ...entry, end_date: "2024" }));
    const update = setEducation(p, "es", edited);

    expect(update.education?.[0].end_date).toBe("2024");
    expect(update.education?.[0].degree).toBe("Bachelor's Degree");
    expect(update.translations?.es?.education?.[0].degree).toBe("Licenciatura");
  });
});

describe("editing in English", () => {
  it("writes straight to the base and leaves Spanish alone", () => {
    const p = profile();
    const update = setHeadline(p, "en", "Staff Engineer");
    expect(update.headline).toBe("Staff Engineer");
    expect(update.translations).toBeUndefined();
  });
});
