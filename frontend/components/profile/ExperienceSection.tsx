import type { ExperienceEntry } from "@/lib/types";
import SectionCard, { EntryCard } from "./SectionCard";
import { FormField, inputClass, textareaClass } from "./FormField";

export default function ExperienceSection({
  experience,
  onChange,
}: {
  experience: ExperienceEntry[];
  onChange: (experience: ExperienceEntry[]) => void;
}) {
  function update(index: number, patch: Partial<ExperienceEntry>) {
    onChange(experience.map((e, i) => (i === index ? { ...e, ...patch } : e)));
  }

  function add() {
    onChange([
      ...experience,
      {
        company: "",
        title: "",
        start_date: "",
        end_date: null,
        location: "",
        bullets: [""],
        skills_used: [],
      },
    ]);
  }

  function remove(index: number) {
    onChange(experience.filter((_, i) => i !== index));
  }

  function updateBullet(expIndex: number, bulletIndex: number, value: string) {
    const entry = experience[expIndex];
    const bullets = entry.bullets.map((b, i) => (i === bulletIndex ? value : b));
    update(expIndex, { bullets });
  }

  function addBullet(expIndex: number) {
    update(expIndex, { bullets: [...experience[expIndex].bullets, ""] });
  }

  function removeBullet(expIndex: number, bulletIndex: number) {
    const bullets = experience[expIndex].bullets.filter((_, i) => i !== bulletIndex);
    update(expIndex, { bullets: bullets.length ? bullets : [""] });
  }

  return (
    <SectionCard
      title="Experience"
      description="Your work history, most recent first."
      onAdd={add}
      addLabel="Experience"
    >
      {experience.length === 0 && (
        <p className="text-sm text-gray-400">No experience yet — add your first role.</p>
      )}
      <div className="space-y-4">
        {experience.map((entry, i) => (
          <EntryCard key={i} onRemove={() => remove(i)}>
            <div className="grid grid-cols-1 gap-2 sm:grid-cols-2">
              <FormField label="Company">
                <input
                  className={inputClass}
                  value={entry.company}
                  onChange={(e) => update(i, { company: e.target.value })}
                />
              </FormField>
              <FormField label="Title">
                <input
                  className={inputClass}
                  value={entry.title}
                  onChange={(e) => update(i, { title: e.target.value })}
                />
              </FormField>
              <FormField label="Start date (YYYY-MM)">
                <input
                  className={inputClass}
                  value={entry.start_date}
                  onChange={(e) => update(i, { start_date: e.target.value })}
                  placeholder="2021-01"
                />
              </FormField>
              <FormField label="End date (blank = present)">
                <input
                  className={inputClass}
                  value={entry.end_date ?? ""}
                  onChange={(e) => update(i, { end_date: e.target.value || null })}
                  placeholder="2023-06"
                />
              </FormField>
              <FormField label="Location" className="sm:col-span-2">
                <input
                  className={inputClass}
                  value={entry.location}
                  onChange={(e) => update(i, { location: e.target.value })}
                />
              </FormField>
            </div>

            <div className="mt-3">
              <span className="mb-1 block text-xs font-medium text-gray-600">
                Bullet points
              </span>
              <div className="space-y-2">
                {entry.bullets.map((bullet, bi) => (
                  <div key={bi} className="flex items-start gap-2">
                    <textarea
                      className={`${textareaClass} min-h-[42px] flex-1`}
                      value={bullet}
                      onChange={(e) => updateBullet(i, bi, e.target.value)}
                      placeholder="Led migration of..."
                      rows={1}
                    />
                    <button
                      type="button"
                      onClick={() => removeBullet(i, bi)}
                      aria-label="Remove bullet"
                      className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-gray-400 hover:bg-gray-100 hover:text-rose-600"
                    >
                      <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M18 6 6 18M6 6l12 12" /></svg>
                    </button>
                  </div>
                ))}
              </div>
              <button
                type="button"
                onClick={() => addBullet(i)}
                className="mt-2 text-xs font-semibold text-brand-600 hover:text-brand-700"
              >
                + Add bullet
              </button>
            </div>

            <FormField label="Skills used (comma-separated)" className="mt-3">
              <input
                className={inputClass}
                value={entry.skills_used.join(", ")}
                onChange={(e) =>
                  update(i, {
                    skills_used: e.target.value
                      .split(",")
                      .map((s) => s.trim())
                      .filter(Boolean),
                  })
                }
                placeholder="C#, SQL, Azure"
              />
            </FormField>
          </EntryCard>
        ))}
      </div>
    </SectionCard>
  );
}
