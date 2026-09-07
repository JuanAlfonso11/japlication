"use client";

import { useState } from "react";
import ErrorNotice from "@/components/ErrorNotice";
import Button from "@/components/ui/Button";
import { inputClass, textareaClass } from "@/components/ui/Field";
import { ApiError, resumeApi } from "@/lib/api";
import type { ResumeVersion } from "@/lib/types";

/** Lets the user correct a generated resume before it becomes a PDF.
 *
 * Generated versions were read-only, so a bullet the adapter got wrong
 * could only be fixed outside the app — and that correction was lost the
 * next time a similar job came up. Saving here stamps the version as
 * edited, which also makes it the preferred starting point for the next
 * similar posting, so the fix is made once.
 *
 * Only the generator's prose is editable. Companies, titles and dates come
 * from the career profile and stay there: letting them drift per-version is
 * how a CV quietly stops matching the profile it claims to be derived from.
 */
export default function ResumeEditor({
  resume,
  onSaved,
  onCancel,
}: {
  resume: ResumeVersion;
  onSaved: (updated: ResumeVersion) => void;
  onCancel: () => void;
}) {
  const [summary, setSummary] = useState(resume.content.summary ?? "");
  const [skills, setSkills] = useState((resume.content.skills ?? []).join(", "));
  const [bullets, setBullets] = useState<string[][]>(
    (resume.content.experience ?? []).map((entry) => [...(entry.bullets ?? [])])
  );
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function updateBullet(entryIndex: number, bulletIndex: number, value: string) {
    setBullets((prev) =>
      prev.map((entry, i) =>
        i === entryIndex ? entry.map((b, j) => (j === bulletIndex ? value : b)) : entry
      )
    );
  }

  function removeBullet(entryIndex: number, bulletIndex: number) {
    setBullets((prev) =>
      prev.map((entry, i) => (i === entryIndex ? entry.filter((_, j) => j !== bulletIndex) : entry))
    );
  }

  function addBullet(entryIndex: number) {
    setBullets((prev) => prev.map((entry, i) => (i === entryIndex ? [...entry, ""] : entry)));
  }

  async function handleSave() {
    setSaving(true);
    setError(null);
    try {
      const experience_bullets: Record<number, string[]> = {};
      bullets.forEach((entryBullets, i) => {
        experience_bullets[i] = entryBullets;
      });

      const updated = await resumeApi.update(resume.id, {
        content: {
          summary,
          skills: skills
            .split(",")
            .map((s) => s.trim())
            .filter(Boolean),
          experience_bullets,
        },
      });
      onSaved(updated);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudieron guardar los cambios.");
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-4">
      {error && <ErrorNotice message={error} />}

      <div>
        <label className="mb-1.5 block text-xs font-semibold text-gray-600 dark:text-gray-400">
          Resumen
        </label>
        <textarea
          value={summary}
          onChange={(e) => setSummary(e.target.value)}
          className={textareaClass}
          placeholder="El párrafo de apertura del CV."
        />
      </div>

      <div>
        <label className="mb-1.5 block text-xs font-semibold text-gray-600 dark:text-gray-400">
          Habilidades
        </label>
        <input
          value={skills}
          onChange={(e) => setSkills(e.target.value)}
          className={inputClass}
          placeholder="Python, PostgreSQL, Docker"
        />
        <p className="mt-1 text-[11px] text-gray-400 dark:text-gray-500">Separadas por comas.</p>
      </div>

      {(resume.content.experience ?? []).map((entry, entryIndex) => (
        <div key={entryIndex}>
          <p className="mb-1.5 text-[10px] font-bold uppercase tracking-[0.08em] text-gray-400 dark:text-gray-500">
            {entry.title} — {entry.company}
          </p>
          <div className="space-y-2">
            {(bullets[entryIndex] ?? []).map((bullet, bulletIndex) => (
              <div key={bulletIndex} className="flex items-start gap-2">
                <textarea
                  value={bullet}
                  onChange={(e) => updateBullet(entryIndex, bulletIndex, e.target.value)}
                  className={`${textareaClass} min-h-[54px]`}
                />
                <button
                  type="button"
                  onClick={() => removeBullet(entryIndex, bulletIndex)}
                  aria-label="Eliminar viñeta"
                  className="mt-1 flex h-8 w-8 shrink-0 items-center justify-center rounded-lg text-gray-400 transition-colors hover:bg-gray-100 hover:text-rose-600 dark:hover:bg-gray-800 dark:hover:text-rose-400"
                >
                  <svg width="15" height="15" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.4" strokeLinecap="round"><path d="M18 6 6 18M6 6l12 12" /></svg>
                </button>
              </div>
            ))}
            <button
              type="button"
              onClick={() => addBullet(entryIndex)}
              className="text-xs font-bold text-brand-600 hover:underline dark:text-brand-400"
            >
              + Agregar viñeta
            </button>
          </div>
        </div>
      ))}

      <div className="flex items-center gap-2 border-t border-gray-100 pt-4 dark:border-gray-800">
        <Button onClick={handleSave} loading={saving} size="sm">
          {saving ? "Guardando…" : "Guardar cambios"}
        </Button>
        <Button variant="ghost" size="sm" onClick={onCancel} disabled={saving}>
          Cancelar
        </Button>
      </div>

      <p className="text-[11px] leading-relaxed text-gray-400 dark:text-gray-500">
        Tus correcciones se reutilizan: la próxima vacante parecida partirá de esta versión en vez de
        generar una nueva desde cero.
      </p>
    </div>
  );
}
