"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { profileApi } from "@/lib/api";
import type { CareerProfile, Job, ScreeningAnswer, User } from "@/lib/types";

/** Leaves what the JobPilot Chrome extension (extension/) needs to fill a form
 * where it can pick it up: localStorage for its next visit, postMessage for a
 * tab where it is already listening. Contact data and the answer bank only,
 * never the token. */
function shareWithExtension(profile: CareerProfile, user: User | null) {
  const c = profile.contact_info;
  const data = {
    full_name: user?.full_name ?? "",
    email: user?.email ?? "",
    phone: c?.phone ?? "",
    city: c?.city ?? "",
    country: c?.country ?? "",
    linkedin: c?.linkedin ?? "",
    github: c?.github ?? "",
    portfolio: c?.portfolio ?? "",
    answers: (profile.screening_answers ?? []).filter((a) => a.answer.trim()),
    synced_at: new Date().toISOString(),
  };
  try {
    window.localStorage.setItem("jobpilot_autofill", JSON.stringify(data));
  } catch {
    // Storage blocked: the postMessage below still reaches a loaded extension.
  }
  window.postMessage({ type: "jobpilot-autofill", data }, window.location.origin);
}

/** Everything you have to retype into someone else's application form,
 * gathered in one place with a copy button on each field.
 *
 * This is JobPilot's answer to what the auto-apply products (JobCopilot,
 * Sorce, Comet) actually sell. Their pitch isn't "we find jobs" — the app
 * already does that better for one person — it's "we stop you retyping the
 * same twelve fields". The difference is that they answer screening
 * questions on the applicant's behalf, which means inventing things the
 * applicant never said; this hands over answers the user wrote themselves,
 * which is the same time saved without the fabrication (and without
 * depending on a form-filling bot that breaks whenever a career site
 * changes its markup — Perplexity shipped that and withdrew it).
 */

function CopyField({ label, value }: { label: string; value: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(value);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      // Clipboard blocked (insecure context, permissions) — the value is
      // still on screen and selectable, so this stays a no-op rather than
      // an error the user can't act on.
    }
  }

  return (
    <button
      type="button"
      onClick={copy}
      title={`Copiar: ${value}`}
      className="group flex w-full items-center gap-2 rounded-xl bg-gray-50 px-3 py-2 text-left transition-colors hover:bg-gray-100 active:scale-[0.99] dark:bg-gray-800/60 dark:hover:bg-gray-800"
    >
      <span className="min-w-0 flex-1">
        <span className="block text-[10px] font-bold uppercase tracking-[0.06em] text-gray-400 dark:text-gray-400">
          {label}
        </span>
        <span className="block truncate text-sm text-gray-800 dark:text-gray-200">{value}</span>
      </span>
      <span
        className={`shrink-0 text-[11px] font-bold transition-colors ${
          copied ? "text-emerald-600 dark:text-emerald-400" : "text-gray-400 group-hover:text-brand-600 dark:group-hover:text-brand-400"
        }`}
      >
        {copied ? "¡Copiado!" : "Copiar"}
      </span>
    </button>
  );
}

const SMALL_BTN =
  "shrink-0 rounded-lg px-2.5 py-1 text-[11px] font-bold transition-colors bg-white text-gray-600 ring-1 ring-inset ring-gray-200 hover:text-brand-600 dark:bg-gray-900 dark:text-gray-300 dark:ring-gray-700 dark:hover:text-brand-400";

function AnswerCard({
  question,
  answer,
  onSave,
}: {
  question: string;
  answer: string;
  onSave: (question: string, answer: string) => Promise<void>;
}) {
  const [copied, setCopied] = useState(false);
  // An empty card is the "add a question" form, so it opens in edit mode.
  const [editing, setEditing] = useState(!answer);
  const [q, setQ] = useState(question);
  const [draft, setDraft] = useState(answer);
  const [saving, setSaving] = useState(false);
  const [error, setError] = useState("");

  async function copy() {
    try {
      await navigator.clipboard.writeText(answer);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      // See CopyField.
    }
  }

  async function save() {
    setSaving(true);
    setError("");
    try {
      await onSave(q.trim(), draft.trim());
      setEditing(false);
    } catch {
      setError("No se pudo guardar. Inténtalo de nuevo.");
    } finally {
      setSaving(false);
    }
  }

  if (editing) {
    return (
      <div className="space-y-2 rounded-xl bg-gray-50 p-3 dark:bg-gray-800/60">
        {question ? (
          <p className="text-xs font-semibold text-gray-500 dark:text-gray-400">{question}</p>
        ) : (
          <input
            value={q}
            onChange={(e) => setQ(e.target.value)}
            placeholder="La pregunta, tal como la hace el formulario"
            aria-label="Pregunta"
            className="w-full rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-xs dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
          />
        )}
        <textarea
          value={draft}
          onChange={(e) => setDraft(e.target.value)}
          rows={3}
          placeholder="Tu respuesta"
          aria-label="Respuesta"
          className="w-full rounded-lg border border-gray-200 bg-white px-2.5 py-1.5 text-sm dark:border-gray-700 dark:bg-gray-900 dark:text-gray-100"
        />
        {error && <p className="text-xs text-rose-600 dark:text-rose-400">{error}</p>}
        <div className="flex justify-end gap-2">
          {answer && (
            <button
              type="button"
              onClick={() => {
                setDraft(answer);
                setEditing(false);
              }}
              className={SMALL_BTN}
            >
              Cancelar
            </button>
          )}
          <button
            type="button"
            onClick={save}
            disabled={saving || !q.trim() || !draft.trim()}
            className="rounded-lg bg-brand-600 px-2.5 py-1 text-[11px] font-bold text-white disabled:opacity-50 dark:bg-brand-200 dark:text-gray-950"
          >
            {saving ? "Guardando…" : "Guardar en mi banco"}
          </button>
        </div>
      </div>
    );
  }

  return (
    <div className="rounded-xl bg-gray-50 p-3 dark:bg-gray-800/60">
      {/* The buttons ride with the question, not with the answer. Beside the
          text they squeezed every answer to about 60% of the width, so each
          one took half a screen to read. */}
      <div className="flex items-start justify-between gap-3">
        <p className="min-w-0 text-xs font-semibold text-gray-500 dark:text-gray-400">{question}</p>
        <div className="flex shrink-0 gap-1.5">
          <button type="button" onClick={() => setEditing(true)} className={SMALL_BTN}>
            Editar
          </button>
          <button
            type="button"
            onClick={copy}
            className={`shrink-0 rounded-lg px-2.5 py-1 text-[11px] font-bold transition-colors ${
              copied
                ? "bg-emerald-50 text-emerald-700 dark:bg-emerald-500/15 dark:text-emerald-300"
                : "bg-white text-gray-600 ring-1 ring-inset ring-gray-200 hover:text-brand-600 dark:bg-gray-900 dark:text-gray-300 dark:ring-gray-700 dark:hover:text-brand-400"
            }`}
          >
            {copied ? "✓" : "Copiar"}
          </button>
        </div>
      </div>
      <p className="mt-1.5 whitespace-pre-line text-sm leading-relaxed text-gray-800 dark:text-gray-200">
        {answer}
      </p>
    </div>
  );
}

export default function ApplicationKit({ job }: { job: Job }) {
  const [profile, setProfile] = useState<CareerProfile | null>(null);
  const [loading, setLoading] = useState(true);
  const [adding, setAdding] = useState(false);
  const { user } = useAuth();

  useEffect(() => {
    let cancelled = false;
    profileApi
      .get()
      .then((p) => {
        if (!cancelled) setProfile(p);
      })
      .catch(() => {
        // No profile yet (404) or a transient failure — the kit simply
        // renders its "set this up" state rather than an error, since it's
        // a convenience panel, not the point of the page.
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  useEffect(() => {
    if (profile) shareWithExtension(profile, user);
  }, [profile, user]);

  /** An edit goes straight into the profile's answer bank, so the next form
   * that asks the same thing -- here or through the extension -- has it. */
  async function saveAnswer(original: string, question: string, answer: string) {
    if (!profile) return;
    const rest = profile.screening_answers.filter((a) => a.question !== original && a.question !== question);
    const updated: ScreeningAnswer[] = [...rest, { question, answer }];
    setProfile(await profileApi.save({ ...profile, screening_answers: updated }));
    setAdding(false);
  }

  if (loading) return null;

  const answers = (profile?.screening_answers ?? []).filter((a) => a.answer.trim().length > 0);
  const contact = profile?.contact_info;

  const contactFields: { label: string; value: string }[] = [];

  if (contact?.phone) contactFields.push({ label: "Teléfono", value: contact.phone });
  if (contact?.city || contact?.country) {
    contactFields.push({
      label: "Ubicación",
      value: [contact.city, contact.country].filter(Boolean).join(", "),
    });
  }
  if (contact?.linkedin) contactFields.push({ label: "LinkedIn", value: contact.linkedin });
  if (contact?.github) contactFields.push({ label: "GitHub", value: contact.github });
  if (contact?.portfolio) contactFields.push({ label: "Portafolio", value: contact.portfolio });

  const isEmpty = answers.length === 0 && contactFields.length === 0;

  return (
    <div className="rounded-2xl bg-white p-5 shadow-soft ring-1 ring-gray-100 dark:bg-gray-900 dark:ring-gray-800">
      <div className="mb-1 flex items-start justify-between gap-3">
        <h2 className="font-display font-bold text-gray-900 dark:text-gray-100">
          Kit de aplicación
        </h2>
        {(job.apply_url || job.source_url) && (
          <a
            href={job.apply_url || job.source_url || undefined}
            target="_blank"
            rel="noreferrer"
            className="shrink-0 text-xs font-bold text-brand-600 hover:underline dark:text-brand-400"
          >
            Abrir formulario ↗
          </a>
        )}
      </div>
      <p className="mb-4 text-xs leading-relaxed text-gray-500 dark:text-gray-400">
        Lo que el formulario te va a volver a pedir, listo para pegar.
      </p>

      {isEmpty ? (
        <div className="rounded-xl bg-gray-50 p-5 text-center dark:bg-gray-800/50">
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Todavía no tienes respuestas guardadas.
          </p>
          <Link
            href="/profile"
            className="mt-3 inline-flex min-h-[36px] items-center rounded-lg bg-brand-600 dark:bg-brand-200 dark:text-gray-950 px-3.5 text-xs font-bold text-white transition-colors hover:bg-brand-700 active:scale-95"
          >
            Configurar en tu perfil
          </Link>
        </div>
      ) : (
        <div className="space-y-4">
          {contactFields.length > 0 && (
            <div>
              <p className="mb-2 text-[10px] font-bold uppercase tracking-[0.08em] text-gray-400 dark:text-gray-400">
                Datos de contacto
              </p>
              <div className="grid grid-cols-1 gap-1.5 sm:grid-cols-2">
                {contactFields.map((f) => (
                  <CopyField key={f.label} label={f.label} value={f.value} />
                ))}
              </div>
            </div>
          )}

          {answers.length > 0 && (
            <div>
              <p className="mb-2 text-[10px] font-bold uppercase tracking-[0.08em] text-gray-400 dark:text-gray-400">
                Respuestas frecuentes
              </p>
              <div className="space-y-2">
                {answers.map((a) => (
                  <AnswerCard
                    key={`${a.question}\n${a.answer}`}
                    question={a.question}
                    answer={a.answer}
                    onSave={(q, ans) => saveAnswer(a.question, q, ans)}
                  />
                ))}
              </div>
            </div>
          )}

          {profile &&
            (adding ? (
              <AnswerCard question="" answer="" onSave={(q, ans) => saveAnswer(q, q, ans)} />
            ) : (
              <button
                type="button"
                onClick={() => setAdding(true)}
                className="block text-xs font-bold text-brand-600 hover:underline dark:text-brand-400"
              >
                + Añadir una pregunta de este formulario
              </button>
            ))}

          <Link
            href="/profile"
            className="inline-block text-xs font-bold text-brand-600 hover:underline dark:text-brand-400"
          >
            Editar respuestas →
          </Link>
        </div>
      )}
    </div>
  );
}
