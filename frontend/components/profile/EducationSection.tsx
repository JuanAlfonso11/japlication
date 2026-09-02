import type { EducationEntry } from "@/lib/types";
import SectionCard, { EntryCard } from "./SectionCard";
import { FormField, inputClass } from "./FormField";

export default function EducationSection({
  education,
  onChange,
}: {
  education: EducationEntry[];
  onChange: (education: EducationEntry[]) => void;
}) {
  function update(index: number, patch: Partial<EducationEntry>) {
    onChange(education.map((e, i) => (i === index ? { ...e, ...patch } : e)));
  }

  function add() {
    onChange([
      ...education,
      { institution: "", degree: "", field: "", start_date: "", end_date: "" },
    ]);
  }

  function remove(index: number) {
    onChange(education.filter((_, i) => i !== index));
  }

  return (
    <SectionCard title="Education" onAdd={add} addLabel="Education">
      {education.length === 0 && (
        <p className="text-sm text-gray-400">No education entries yet.</p>
      )}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {education.map((entry, i) => (
          <EntryCard key={i} onRemove={() => remove(i)}>
            <div className="grid grid-cols-2 gap-2">
              <FormField label="Institution" className="col-span-2">
                <input
                  className={inputClass}
                  value={entry.institution}
                  onChange={(e) => update(i, { institution: e.target.value })}
                />
              </FormField>
              <FormField label="Degree">
                <input
                  className={inputClass}
                  value={entry.degree}
                  onChange={(e) => update(i, { degree: e.target.value })}
                />
              </FormField>
              <FormField label="Field of study">
                <input
                  className={inputClass}
                  value={entry.field}
                  onChange={(e) => update(i, { field: e.target.value })}
                />
              </FormField>
              <FormField label="Start date">
                <input
                  className={inputClass}
                  value={entry.start_date}
                  onChange={(e) => update(i, { start_date: e.target.value })}
                  placeholder="2016-09"
                />
              </FormField>
              <FormField label="End date">
                <input
                  className={inputClass}
                  value={entry.end_date}
                  onChange={(e) => update(i, { end_date: e.target.value })}
                  placeholder="2020-06"
                />
              </FormField>
            </div>
          </EntryCard>
        ))}
      </div>
    </SectionCard>
  );
}
