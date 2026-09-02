import type { CertificationEntry } from "@/lib/types";
import SectionCard, { EntryCard } from "./SectionCard";
import { FormField, inputClass } from "./FormField";

export default function CertificationsSection({
  certifications,
  onChange,
}: {
  certifications: CertificationEntry[];
  onChange: (certifications: CertificationEntry[]) => void;
}) {
  function update(index: number, patch: Partial<CertificationEntry>) {
    onChange(certifications.map((c, i) => (i === index ? { ...c, ...patch } : c)));
  }

  function add() {
    onChange([...certifications, { name: "", issuer: "", date: "" }]);
  }

  function remove(index: number) {
    onChange(certifications.filter((_, i) => i !== index));
  }

  return (
    <SectionCard title="Certifications" onAdd={add} addLabel="Certification">
      {certifications.length === 0 && (
        <p className="text-sm text-gray-400">No certifications yet.</p>
      )}
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {certifications.map((entry, i) => (
          <EntryCard key={i} onRemove={() => remove(i)}>
            <div className="grid grid-cols-2 gap-2">
              <FormField label="Name" className="col-span-2">
                <input
                  className={inputClass}
                  value={entry.name}
                  onChange={(e) => update(i, { name: e.target.value })}
                />
              </FormField>
              <FormField label="Issuer">
                <input
                  className={inputClass}
                  value={entry.issuer}
                  onChange={(e) => update(i, { issuer: e.target.value })}
                />
              </FormField>
              <FormField label="Date">
                <input
                  className={inputClass}
                  value={entry.date}
                  onChange={(e) => update(i, { date: e.target.value })}
                  placeholder="2023-04"
                />
              </FormField>
            </div>
          </EntryCard>
        ))}
      </div>
    </SectionCard>
  );
}
