import type { LanguageEntry } from "@/lib/types";
import SectionCard, { EntryCard } from "./SectionCard";
import { FormField, inputClass } from "./FormField";

export default function LanguagesSection({
  languages,
  onChange,
}: {
  languages: LanguageEntry[];
  onChange: (languages: LanguageEntry[]) => void;
}) {
  function update(index: number, patch: Partial<LanguageEntry>) {
    onChange(languages.map((l, i) => (i === index ? { ...l, ...patch } : l)));
  }

  function add() {
    onChange([...languages, { name: "", level: "" }]);
  }

  function remove(index: number) {
    onChange(languages.filter((_, i) => i !== index));
  }

  return (
    <SectionCard title="Languages" onAdd={add} addLabel="Language">
      {languages.length === 0 && <p className="text-sm text-gray-400">No languages yet.</p>}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {languages.map((entry, i) => (
          <EntryCard key={i} onRemove={() => remove(i)}>
            <div className="grid grid-cols-2 gap-2">
              <FormField label="Language">
                <input
                  className={inputClass}
                  value={entry.name}
                  onChange={(e) => update(i, { name: e.target.value })}
                  placeholder="English"
                />
              </FormField>
              <FormField label="Level">
                <input
                  className={inputClass}
                  value={entry.level}
                  onChange={(e) => update(i, { level: e.target.value })}
                  placeholder="C1, Native…"
                />
              </FormField>
            </div>
          </EntryCard>
        ))}
      </div>
    </SectionCard>
  );
}
