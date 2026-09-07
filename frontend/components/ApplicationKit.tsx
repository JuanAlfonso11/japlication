"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { profileApi } from "@/lib/api";
import type { CareerProfile, Job } from "@/lib/types";

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
        <span className="block text-[10px] font-bold uppercase tracking-[0.06em] text-gray-400 dark:text-gray-500">
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

function AnswerCard({ question, answer }: { question: string; answer: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(answer);
      setCopied(true);
      setTimeout(() => setCopied(false), 1600);
    } catch {
      // See CopyField.
    }
  }

  return (
    <div className="rounded-xl bg-gray-50 p-3 dark:bg-gray-800/60">
      <p className="text-xs font-semibold text-gray-500 dark:text-gray-400">{question}</p>
      <div className="mt-1.5 flex items-start justify-between gap-3">
        <p className="min-w-0 flex-1 whitespace-pre-line text-sm leading-relaxed text-gray-800 dark:text-gray-200">
          {answer}
        </p>
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
  );
}

export default function ApplicationKit({ job }: { job: Job }) {
  const [profile, setProfile] = useState<CareerProfile | null>(null);
  const [loading, setLoading] = useState(true);

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
        {job.source_url && (
          <a
            href={job.source_url}
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
            className="mt-3 inline-flex min-h-[36px] items-center rounded-lg bg-brand-600 px-3.5 text-xs font-bold text-white transition-colors hover:bg-brand-700 active:scale-95"
          >
            Configurar en tu perfil
          </Link>
        </div>
      ) : (
        <div className="space-y-4">
          {contactFields.length > 0 && (
            <div>
              <p className="mb-2 text-[10px] font-bold uppercase tracking-[0.08em] text-gray-400 dark:text-gray-500">
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
              <p className="mb-2 text-[10px] font-bold uppercase tracking-[0.08em] text-gray-400 dark:text-gray-500">
                Respuestas frecuentes
              </p>
              <div className="space-y-2">
                {answers.map((a, i) => (
                  <AnswerCard key={i} question={a.question} answer={a.answer} />
                ))}
              </div>
            </div>
          )}

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
