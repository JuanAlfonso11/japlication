import type { Skill } from "@/lib/types";
import SectionCard, { EntryCard } from "./SectionCard";
import { FormField, inputClass, Select } from "./FormField";

const LEVELS = ["beginner", "intermediate", "advanced", "expert"];
const LEVEL_LABELS: Record<string, string> = {
  beginner: "Principiante",
  intermediate: "Intermedio",
  advanced: "Avanzado",
  expert: "Experto",
};

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
      title="Habilidades"
      description="Habilidades técnicas y blandas usadas para calcular el match."
      onAdd={add}
      addLabel="Habilidad"
    >
      {skills.length === 0 && (
        <p className="text-sm text-gray-400">Todavía no hay habilidades — agrega la primera.</p>
      )}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {skills.map((skill, i) => (
          <EntryCard key={i} onRemove={() => remove(i)}>
            {/* Two rows of two, not four stacked: with 37 skills, a card per
                skill at four full-width fields made "Mi CV" a screen you
                scroll past rather than read. Same four fields, half the
                height. */}
            <div className="grid grid-cols-2 gap-2">
              <FormField label="Nombre">
                <input
                  className={inputClass}
                  value={skill.name}
                  onChange={(e) => update(i, { name: e.target.value })}
                  placeholder="ej. TypeScript"
                />
              </FormField>
              <FormField label="Nivel">
                <Select
                  value={skill.level}
                  onChange={(e) => update(i, { level: e.target.value })}
                >
                  {LEVELS.map((l) => (
                    <option key={l} value={l}>
                      {LEVEL_LABELS[l]}
                    </option>
                  ))}
                </Select>
              </FormField>
              <FormField label="Categoría">
                <input
                  className={inputClass}
                  value={skill.category}
                  onChange={(e) => update(i, { category: e.target.value })}
                  placeholder="lenguaje, herramienta…"
                />
              </FormField>
              {/* "Años", not "Años de experiencia": at half width that label
                  wrapped to two lines and undid the height this saves. */}
              <FormField label="Años">
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
