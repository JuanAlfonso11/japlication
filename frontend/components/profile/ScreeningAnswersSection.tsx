import { COMMON_SCREENING_QUESTIONS, type ScreeningAnswer } from "@/lib/types";
import SectionCard, { EntryCard } from "./SectionCard";
import { FormField, inputClass } from "./FormField";

/** The answer bank behind the per-job application kit.
 *
 * This is the profile's only section that isn't part of the CV itself —
 * it's the stuff forms ask that a résumé doesn't carry (work
 * authorization, notice period, salary expectation). Every application
 * asks them again, which is the busywork the auto-apply products charge
 * for; writing them once here means the kit can hand them over with a copy
 * button instead of a bot inventing answers on the user's behalf. */
export default function ScreeningAnswersSection({
  answers,
  onChange,
}: {
  answers: ScreeningAnswer[];
  onChange: (answers: ScreeningAnswer[]) => void;
}) {
  function update(index: number, patch: Partial<ScreeningAnswer>) {
    onChange(answers.map((a, i) => (i === index ? { ...a, ...patch } : a)));
  }

  function add() {
    onChange([...answers, { question: "", answer: "" }]);
  }

  function remove(index: number) {
    onChange(answers.filter((_, i) => i !== index));
  }

  /** Adds the standard questions the user hasn't already got, leaving the
   * answers blank — the point is to save them from remembering what forms
   * ask, never to put words in their mouth. */
  function seedCommon() {
    const existing = new Set(answers.map((a) => a.question.trim().toLowerCase()));
    const missing = COMMON_SCREENING_QUESTIONS.filter(
      (q) => !existing.has(q.trim().toLowerCase())
    ).map((question) => ({ question, answer: "" }));
    if (missing.length > 0) onChange([...answers, ...missing]);
  }

  const answered = answers.filter((a) => a.answer.trim().length > 0).length;

  return (
    <SectionCard
      title="Respuestas frecuentes"
      description="Lo que todo formulario vuelve a preguntar. Se responde una vez acá y queda listo para copiar en cada vacante."
      onAdd={add}
      addLabel="Pregunta"
    >
      {answers.length === 0 ? (
        <div className="rounded-xl bg-gray-50 p-5 text-center dark:bg-gray-800/50">
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Todavía no tienes respuestas guardadas.
          </p>
          <button
            type="button"
            onClick={seedCommon}
            className="mt-3 inline-flex min-h-[36px] items-center rounded-lg bg-brand-600 dark:bg-brand-200 dark:text-gray-950 px-3.5 text-xs font-bold text-white transition-colors hover:bg-brand-700 active:scale-95"
          >
            Empezar con las {COMMON_SCREENING_QUESTIONS.length} más comunes
          </button>
        </div>
      ) : (
        <>
          <p className="tabular text-xs font-medium text-gray-400 dark:text-gray-400">
            {answered} de {answers.length} respondidas
          </p>
          <div className="space-y-3">
            {answers.map((entry, i) => (
              <EntryCard key={i} onRemove={() => remove(i)}>
                <FormField
                  label={
                    entry.answer.trim().length > 0 ? (
                      "Pregunta"
                    ) : (
                      <>
                        Pregunta{" "}
                        <span className="ml-1 rounded-full bg-amber-50 px-1.5 py-0.5 text-[10px] font-bold uppercase tracking-wide text-amber-700 dark:bg-amber-900/30 dark:text-amber-300">
                          Pendiente
                        </span>
                      </>
                    )
                  }
                >
                  {/* Wraps instead of truncating: on a single line these read
                      "¿Tienes autorización para trabaja…", and a question you
                      cannot read is one you cannot answer. Marking the
                      unanswered ones in place beats sorting them first — the
                      save path addresses each row by its index. */}
                  <textarea
                    rows={2}
                    className={`${inputClass} resize-y py-2 leading-snug`}
                    value={entry.question}
                    onChange={(e) => update(i, { question: e.target.value })}
                    placeholder="¿Cuál es tu expectativa salarial?"
                  />
                </FormField>
                <FormField label="Tu respuesta" className="mt-2">
                  <textarea
                    className={`${inputClass} min-h-[64px] resize-y py-2 leading-relaxed`}
                    value={entry.answer}
                    onChange={(e) => update(i, { answer: e.target.value })}
                    placeholder="Escríbela una vez y reutilízala en cada postulación."
                  />
                </FormField>
              </EntryCard>
            ))}
          </div>
          <button
            type="button"
            onClick={seedCommon}
            className="text-xs font-bold text-brand-600 hover:underline dark:text-brand-400"
          >
            + Agregar las preguntas comunes que falten
          </button>
        </>
      )}
    </SectionCard>
  );
}
