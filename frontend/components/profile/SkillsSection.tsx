import type { Skill } from "@/lib/types";
import SectionCard, { EntryCard } from "./SectionCard";
import { FormField, inputClass, Select } from "./FormField";

const LEVELS = ["beginner", "intermediate", "advanced", "expert"];

export default function SkillsSection({
  skills,
  onChange,
}: {
  skills: Skill[];
  onChange: (skills: Skill[]) => void;
}) {
  function update(index: number, patch: Partial<Skill>) {
    onChange(skills.map((s, i) => (i === index ? { ...s, ...patch } : s)));
  }

  function add() {
    onChange([
      ...skills,
      { name: "", category: "", level: "intermediate", years_experience: null },
    ]);
  }

  function remove(index: number) {
    onChange(skills.filter((_, i) => i !== index));
  }

  return (
    <SectionCard
      title="Skills"
      description="Technical and soft skills used for match scoring."
      onAdd={add}
      addLabel="Skill"
    >
      {skills.length === 0 && (
        <p className="text-sm text-gray-400">No skills yet — add your first one.</p>
      )}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {skills.map((skill, i) => (
          <EntryCard key={i} onRemove={() => remove(i)}>
            <div className="grid grid-cols-2 gap-2">
              <FormField label="Name" className="col-span-2">
                <input
                  className={inputClass}
                  value={skill.name}
                  onChange={(e) => update(i, { name: e.target.value })}
                  placeholder="e.g. TypeScript"
                />
              </FormField>
              <FormField label="Category">
                <input
                  className={inputClass}
                  value={skill.category}
                  onChange={(e) => update(i, { category: e.target.value })}
                  placeholder="language, tool…"
                />
              </FormField>
              <FormField label="Level">
                <Select
                  value={skill.level}
                  onChange={(e) => update(i, { level: e.target.value })}
                >
                  {LEVELS.map((l) => (
                    <option key={l} value={l}>
                      {l}
                    </option>
                  ))}
                </Select>
              </FormField>
              <FormField label="Years of experience" className="col-span-2">
                <input
                  type="number"
                  min={0}
                  step={0.5}
                  className={inputClass}
                  value={skill.years_experience ?? ""}
                  onChange={(e) =>
                    update(i, {
                      years_experience: e.target.value === "" ? null : Number(e.target.value),
                    })
                  }
                />
              </FormField>
            </div>
          </EntryCard>
        ))}
      </div>
    </SectionCard>
  );
}
