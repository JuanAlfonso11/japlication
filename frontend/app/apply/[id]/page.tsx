"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useCallback, useEffect, useMemo, useState } from "react";
import CollapsibleText from "@/components/CollapsibleText";
import ErrorNotice from "@/components/ErrorNotice";
import RouteGuard from "@/components/RouteGuard";
import Button, { buttonClass } from "@/components/ui/Button";
import { inputClass, Select, textareaClass } from "@/components/ui/Field";
import { ListSkeleton } from "@/components/ui/Skeleton";
import { ApiError, applicationsApi, applyAgentApi, coverLetterApi, resumeApi } from "@/lib/api";
import {
  DRAFT_STATUS_LABELS,
  DRAFT_STATUS_TONE,
  SOURCE_LABELS,
  TONE_CLASSES,
  describeDraft,
  groupFields,
  isMoving,
} from "@/lib/applyDraft";
import { refreshWidgets } from "@/lib/widgets";
import type { Application, ApplicationDraft, CoverLetter, DraftField } from "@/lib/types";

const KIND_HINTS: Record<string, string> = {
  consent: "Declaración o consentimiento: es tu firma, por eso la marcas tú.",
  sensitive: "Pregunta sensible: si es voluntaria puedes dejarla en blanco.",
  personal: "Sobre tu historial o tus relaciones: tu perfil no lo registra.",
  work_auth: "Autorización de trabajo o visa: contesta según dónde trabajarías.",
  salary: "Salario: revisa la cifra antes de enviar.",
};

/** El valor que el formulario manda para la opción elegida (o el texto). */
function initialValue(f: DraftField): unknown {
  if (f.status !== "filled") return f.type === "multiselect" ? [] : "";
  return f.value ?? (f.type === "multiselect" ? [] : "");
}

function FieldInput({
  field,
  value,
  onChange,
}: {
  field: DraftField;
  value: unknown;
  onChange: (v: unknown) => void;
}) {
  const id = `f-${field.key}`;
  if (field.type === "select") {
    return (
      <Select id={id} value={value == null ? "" : String(value)} onChange={(e) => onChange(e.target.value)}>
        <option value="">— Elige —</option>
        {field.options.map((o) => (
          <option key={String(o.value)} value={String(o.value)}>
            {o.label}
          </option>
        ))}
      </Select>
    );
  }
  if (field.type === "multiselect") {
    const elegidos = new Set((Array.isArray(value) ? value : []).map(String));
    return (
      <div className="space-y-1">
        {field.options.map((o) => {
          const v = String(o.value);
          return (
            <label key={v} className="flex min-h-[36px] items-center gap-2 text-sm text-gray-700 dark:text-gray-200">
              <input
                type="checkbox"
                checked={elegidos.has(v)}
                onChange={(e) => {
                  const next = new Set(elegidos);
                  if (e.target.checked) next.add(v);
                  else next.delete(v);
                  onChange(Array.from(next));
                }}
                className="h-4 w-4 rounded border-gray-300"
              />
              {o.label}
            </label>
          );
        })}
      </div>
    );
  }
  if (field.type === "textarea") {
    return (
      <textarea
        id={id}
        className={textareaClass}
        value={String(value ?? "")}
        maxLength={2000}
        onChange={(e) => onChange(e.target.value)}
      />
    );
  }
  return (
    <input
      id={id}
      className={inputClass}
      value={String(value ?? "")}
      maxLength={300}
      onChange={(e) => onChange(e.target.value)}
    />
  );
}

function FieldRow({
  field,
  editing,
  value,
  onEdit,
  onChange,
}: {
  field: DraftField;
  editing: boolean;
  value: unknown;
  onEdit: () => void;
  onChange: (v: unknown) => void;
}) {
  const hint = KIND_HINTS[field.kind];
  return (
    <li className="rounded-xl bg-gray-50 p-3 dark:bg-gray-800/50">
      <div className="flex items-start justify-between gap-2">
        <label htmlFor={`f-${field.key}`} className="text-sm font-semibold text-gray-800 dark:text-gray-100">
          {field.label}
          {field.required && <span className="text-rose-500"> *</span>}
        </label>
        {!editing && field.type !== "file" && (
          <button
            type="button"
            onClick={onEdit}
            className="shrink-0 text-xs font-bold text-brand-600 hover:underline dark:text-brand-300"
          >
            Cambiar
          </button>
        )}
      </div>
      {editing ? (
        <div className="mt-2 space-y-1.5">
          <FieldInput field={field} value={value} onChange={onChange} />
          {(hint || field.reason) && (
            <p className="text-[11px] leading-relaxed text-gray-500 dark:text-gray-400">{hint ?? field.reason}</p>
          )}
        </div>
      ) : (
        <div className="mt-1">
          <p className="whitespace-pre-line text-sm text-gray-700 dark:text-gray-300">
            {field.display || <span className="italic text-gray-400">En blanco</span>}
          </p>
          {SOURCE_LABELS[field.source] && (
            <p className="mt-0.5 text-[11px] text-gray-400 dark:text-gray-500">{SOURCE_LABELS[field.source]}</p>
          )}
        </div>
      )}
    </li>
  );
}

function Section({ title, children, subtitle }: { title: string; subtitle?: string; children: React.ReactNode }) {
  return (
    <section className="space-y-2.5 rounded-2xl bg-white p-4 shadow-sm ring-1 ring-gray-100 dark:bg-gray-900 dark:ring-gray-800">
      <div>
        <h2 className="font-semibold text-gray-900 dark:text-gray-100">{title}</h2>
        {subtitle && <p className="mt-0.5 text-xs text-gray-500 dark:text-gray-400">{subtitle}</p>}
      </div>
      {children}
    </section>
  );
}

function ReviewContent() {
  const params = useParams<{ id: string }>();
  const applicationId = params.id;
  const [draft, setDraft] = useState<ApplicationDraft | null>(null);
  const [application, setApplication] = useState<Application | null>(null);
  const [carta, setCarta] = useState<CoverLetter | null>(null);
  const [loadError, setLoadError] = useState<string | null>(null);
  const [actionError, setActionError] = useState<string | null>(null);
  const [busy, setBusy] = useState<string | null>(null);
  const [answers, setAnswers] = useState<Record<string, unknown>>({});
  const [editingKeys, setEditingKeys] = useState<Set<string>>(new Set());
  const [confirming, setConfirming] = useState(false);

  const load = useCallback(async () => {
    try {
      const d = await applyAgentApi.get(applicationId);
      setDraft(d);
      setLoadError(null);
      return d;
    } catch (err) {
      if (err instanceof ApiError && err.status === 404) {
        setLoadError("Esta vacante todavía no tiene una aplicación preparada.");
      } else {
        setLoadError(err instanceof ApiError ? err.message : "No se pudo cargar la aplicación.");
      }
      return null;
    }
  }, [applicationId]);

  useEffect(() => {
    applicationsApi.get(applicationId).then(setApplication).catch(() => undefined);
  }, [applicationId]);

  // Mientras se prepara o se envía, vuelve a preguntar.
  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | undefined;
    let cancelled = false;
    async function tick() {
      const d = await load();
      if (!cancelled && d && isMoving(d.status)) timer = setTimeout(tick, 2000);
    }
    tick();
    return () => {
      cancelled = true;
      if (timer) clearTimeout(timer);
    };
  }, [load]);

  useEffect(() => {
    if (!draft?.cover_letter_id) return;
    coverLetterApi.get(draft.cover_letter_id).then(setCarta).catch(() => undefined);
  }, [draft?.cover_letter_id]);

  const fields = useMemo(() => draft?.content.fields ?? [], [draft]);
  const groups = useMemo(() => groupFields(fields), [fields]);

  // Los pendientes siempre se editan; el resto, al tocar "Cambiar".
  const isEditing = (f: DraftField) => groups.pending.includes(f) || editingKeys.has(f.key);
  const valueOf = (f: DraftField) => (f.key in answers ? answers[f.key] : initialValue(f));
  const setValue = (f: DraftField, v: unknown) => setAnswers((a) => ({ ...a, [f.key]: v }));
  const dirty = Object.keys(answers).length > 0;

  async function run<T>(label: string, fn: () => Promise<T>): Promise<T | null> {
    setBusy(label);
    setActionError(null);
    try {
      return await fn();
    } catch (err) {
      setActionError(err instanceof ApiError ? err.message : "Algo falló. Intenta de nuevo.");
      return null;
    } finally {
      setBusy(null);
    }
  }

  async function saveAnswers(): Promise<ApplicationDraft | null> {
    if (!dirty) return draft;
    const d = await run("save", () => applyAgentApi.answer(applicationId, answers));
    if (d) {
      setDraft(d);
      setAnswers({});
      setEditingKeys(new Set());
    }
    return d;
  }

  async function submit() {
    setConfirming(false);
    const saved = await saveAnswers();
    if (!saved) return;
    const d = await run("submit", () => applyAgentApi.submit(applicationId));
    if (d) {
      setDraft(d);
      refreshWidgets();
    }
  }

  async function reviewedLetter(ok: boolean) {
    const d = await run("letter", () => applyAgentApi.answer(applicationId, {}, ok));
    if (d) setDraft(d);
  }

  if (loadError && !draft) {
    return (
      <div className="mx-auto max-w-2xl space-y-3">
        <ErrorNotice message={loadError} onRetry={load} />
        {application && (
          <Button
            onClick={async () => {
              const d = await run("prepare", () => applyAgentApi.prepare(applicationId));
              if (d) {
                setDraft(d);
                setLoadError(null);
              }
            }}
            loading={busy === "prepare"}
          >
            Preparar la aplicación ahora
          </Button>
        )}
      </div>
    );
  }
  if (!draft) return <ListSkeleton rows={4} />;

  const c = draft.content;
  const status = draft.status;
  const title = c.title || application?.job?.title || "Vacante";
  const company = c.company || application?.job?.company || "";
  const pagina = draft.form_url || c.url || null;
  const pendientes = groups.pending.filter((f) => f.required).length;
  const puedeEnviar = (status === "ready" || status === "scheduled") && pendientes === 0;
  const bloqueos = (c.gates ?? []).filter((g) => g.level === "block");
  const avisos = (c.gates ?? []).filter((g) => g.level === "warn");
  const cartaDoc = c.documents?.cover_letter;
  const final = status === "submitted" || status === "cancelled";

  return (
    <div className="mx-auto max-w-2xl space-y-4 animate-fade-in">
      <div>
        <Link href="/apply" className="text-xs font-bold text-gray-500 hover:underline dark:text-gray-400">
          ← Aplicaciones
        </Link>
        <h1 className="mt-1 font-display text-[24px] font-extrabold leading-tight tracking-display-tight text-gray-900 dark:text-gray-50">
          {title}
        </h1>
        <p className="text-sm text-gray-500 dark:text-gray-400">
          {company}
          {draft.channel === "email" ? " · se envía por correo" : draft.channel === "greenhouse" ? " · formulario de Greenhouse" : " · se envía en su página"}
        </p>
        <div className="mt-2 flex flex-wrap items-center gap-2">
          <span className={`inline-flex items-center gap-1.5 rounded-full px-2 py-0.5 text-[11px] font-bold ring-1 ring-inset ${TONE_CLASSES[DRAFT_STATUS_TONE[status]]}`}>
            {isMoving(status) && <span aria-hidden="true" className="h-1.5 w-1.5 animate-pulse rounded-full bg-current" />}
            {DRAFT_STATUS_LABELS[status]}
          </span>
          {application?.job_id && (
            <Link href={`/jobs/${application.job_id}`} className="text-xs font-bold text-brand-600 hover:underline dark:text-brand-300">
              Ver la vacante
            </Link>
          )}
        </div>
        <p className="mt-2 text-sm leading-relaxed text-gray-700 dark:text-gray-300" aria-live="polite">
          {describeDraft({
            status,
            pending_count: pendientes,
            handoff_reason: c.handoff_reason ?? null,
            error: draft.error,
            scheduled_for: draft.scheduled_for,
            channel: draft.channel,
          })}
        </p>
        {c.channel_notice && <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">{c.channel_notice}</p>}
        {c.auto_limit_reached && (
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
            Ya salieron solas todas las de hoy: esta espera tu toque.
          </p>
        )}
      </div>

      {actionError && <ErrorNotice message={actionError} />}

      {(bloqueos.length > 0 || avisos.length > 0) && (
        <Section title="Requisitos de la oferta" subtitle="Con la frase de la oferta, para que decidas tú.">
          <ul className="space-y-2">
            {[...bloqueos, ...avisos].map((g) => (
              <li
                key={g.code}
                className={`rounded-xl p-3 text-sm ring-1 ring-inset ${
                  g.level === "block"
                    ? "bg-rose-50 text-rose-900 ring-rose-200 dark:bg-rose-500/10 dark:text-rose-200 dark:ring-rose-500/25"
                    : "bg-amber-50 text-amber-900 ring-amber-200 dark:bg-amber-500/10 dark:text-amber-200 dark:ring-amber-500/25"
                }`}
              >
                <p className="font-semibold">{g.message}</p>
                {g.evidence.map((e) => (
                  <p key={e} className="mt-1 text-xs italic opacity-80">«{e}»</p>
                ))}
              </li>
            ))}
          </ul>
        </Section>
      )}

      {c.grounding && (c.grounding.issues.length > 0 || c.grounding.fixed.length > 0) && (
        <Section
          title="Revisión de hechos"
          subtitle="Tu CV y tu carta comparados con tu perfil: nada sale con algo que no dijiste."
        >
          <ul className="space-y-1.5 text-sm">
            {c.grounding.issues.map((i) => (
              <li key={i} className="text-rose-700 dark:text-rose-300">• {i}</li>
            ))}
            {c.grounding.fixed.map((i) => (
              <li key={i} className="text-gray-600 dark:text-gray-400">✓ {i}</li>
            ))}
          </ul>
          {c.grounding.issues.length > 0 && application?.job_id && (
            <Link href={`/jobs/${application.job_id}`} className={buttonClass({ size: "sm", variant: "secondary" })}>
              Corregir el CV o la carta
            </Link>
          )}
        </Section>
      )}

      <Section title="Lo que se envía">
        <ul className="space-y-2 text-sm">
          {draft.resume_version_id && (
            <li className="flex items-center justify-between gap-2 rounded-xl bg-gray-50 p-3 dark:bg-gray-800/50">
              <span className="text-gray-700 dark:text-gray-200">Tu CV para esta vacante</span>
              <button
                type="button"
                className="text-xs font-bold text-brand-600 hover:underline dark:text-brand-300"
                onClick={() =>
                  run("cv", () => resumeApi.downloadPdf(draft.resume_version_id as string, `CV - ${company}.pdf`))
                }
              >
                Ver PDF
              </button>
            </li>
          )}
          {carta && (
            <li className="rounded-xl bg-gray-50 p-3 dark:bg-gray-800/50">
              <p className="mb-1 text-gray-700 dark:text-gray-200">
                Carta de presentación
                {cartaDoc?.generated_by === "ai" && (
                  <span className="ml-1.5 text-[11px] text-gray-400">(redactada por la IA)</span>
                )}
              </p>
              <CollapsibleText text={carta.content} />
              {cartaDoc?.generated_by === "ai" && !final && (
                <label className="mt-2 flex min-h-[36px] items-center gap-2 text-xs font-semibold text-gray-700 dark:text-gray-200">
                  <input
                    type="checkbox"
                    checked={!!cartaDoc.reviewed}
                    disabled={busy === "letter"}
                    onChange={(e) => reviewedLetter(e.target.checked)}
                    className="h-4 w-4 rounded border-gray-300"
                  />
                  La leí y está bien
                </label>
              )}
            </li>
          )}
          {draft.channel === "email" && c.email && (
            <li className="rounded-xl bg-gray-50 p-3 text-xs text-gray-600 dark:bg-gray-800/50 dark:text-gray-300">
              <p><strong>Para:</strong> {c.email.to}</p>
              <p><strong>Asunto:</strong> {c.email.subject}</p>
              {c.email.blockers.map((b) => (
                <p key={b} className="mt-1 text-rose-700 dark:text-rose-300">{b}</p>
              ))}
            </li>
          )}
        </ul>
      </Section>

      {groups.pending.length > 0 && (
        <Section
          title={`Te falta responder (${groups.pending.length})`}
          subtitle="Lo que tu perfil no contesta o solo tú puedes decir. Se guarda solo en esta aplicación."
        >
          <ul className="space-y-2">
            {groups.pending.map((f) => (
              <FieldRow key={f.key} field={f} editing value={valueOf(f)} onEdit={() => undefined} onChange={(v) => setValue(f, v)} />
            ))}
          </ul>
        </Section>
      )}

      {groups.byAi.length > 0 && (
        <Section title="Respondidas por la IA" subtitle="Solo con datos de tu perfil. Léelas: van con tu nombre.">
          <ul className="space-y-2">
            {groups.byAi.map((f) => (
              <FieldRow
                key={f.key}
                field={f}
                editing={isEditing(f)}
                value={valueOf(f)}
                onEdit={() => setEditingKeys((s) => new Set(s).add(f.key))}
                onChange={(v) => setValue(f, v)}
              />
            ))}
          </ul>
        </Section>
      )}

      {groups.filled.length > 0 && (
        <details className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-gray-100 dark:bg-gray-900 dark:ring-gray-800">
          <summary className="cursor-pointer font-semibold text-gray-900 dark:text-gray-100">
            Llenadas con tu perfil ({groups.filled.length})
          </summary>
          <ul className="mt-3 space-y-2">
            {groups.filled.map((f) => (
              <FieldRow
                key={f.key}
                field={f}
                editing={isEditing(f)}
                value={valueOf(f)}
                onEdit={() => setEditingKeys((s) => new Set(s).add(f.key))}
                onChange={(v) => setValue(f, v)}
              />
            ))}
          </ul>
        </details>
      )}

      {groups.skipped.length > 0 && (
        <details className="rounded-2xl bg-white p-4 shadow-sm ring-1 ring-gray-100 dark:bg-gray-900 dark:ring-gray-800">
          <summary className="cursor-pointer font-semibold text-gray-900 dark:text-gray-100">
            Se dejan en blanco ({groups.skipped.length})
          </summary>
          <p className="mt-1 text-xs text-gray-500 dark:text-gray-400">
            Opcionales que el agente no responde por ti (por ejemplo, las de diversidad). Puedes contestarlas si quieres.
          </p>
          <ul className="mt-3 space-y-2">
            {groups.skipped.map((f) => (
              <FieldRow
                key={f.key}
                field={f}
                editing={isEditing(f)}
                value={valueOf(f)}
                onEdit={() => setEditingKeys((s) => new Set(s).add(f.key))}
                onChange={(v) => setValue(f, v)}
              />
            ))}
          </ul>
        </details>
      )}

      {(c.review_reason_texts ?? []).length > 0 && !final && (
        <Section title="Por qué no sale sola">
          <ul className="space-y-1 text-xs text-gray-600 dark:text-gray-300">
            {(c.review_reason_texts ?? []).map((t) => (
              <li key={t}>• {t}</li>
            ))}
          </ul>
        </Section>
      )}

      {!final && !isMoving(status) && (
        // Pegada al pie, encima de la barra de pestañas del teléfono (58 px +
        // el borde seguro): las acciones siempre al alcance del pulgar, sin
        // tapar el final de la página como haría un `fixed`.
        <div className="sticky bottom-[calc(58px+env(safe-area-inset-bottom))] z-30 -mx-4 border-t border-gray-100 bg-white/95 px-4 py-3 backdrop-blur md:bottom-0 md:mx-0 md:rounded-2xl md:border md:shadow-soft dark:border-gray-800 dark:bg-gray-950/95">
          <div className="flex flex-wrap items-center justify-end gap-2">
            {status !== "handoff" && (
              <Button
                variant="ghost"
                size="sm"
                loading={busy === "cancel"}
                onClick={async () => {
                  const d = await run("cancel", () => applyAgentApi.cancel(applicationId));
                  if (d) setDraft(d);
                }}
              >
                {status === "scheduled" ? "Deshacer" : "Descartar"}
              </Button>
            )}
            <Button
              variant="ghost"
              size="sm"
              loading={busy === "prepare"}
              onClick={async () => {
                const d = await run("prepare", () => applyAgentApi.prepare(applicationId));
                if (d) {
                  setDraft(d);
                  setAnswers({});
                }
              }}
            >
              Rehacer
            </Button>
            {dirty && (
              <Button variant="secondary" size="sm" loading={busy === "save"} onClick={saveAnswers}>
                Guardar respuestas
              </Button>
            )}
            {status === "handoff" ? (
              <>
                {pagina && (
                  <a href={pagina} target="_blank" rel="noreferrer" className={buttonClass({ size: "sm", variant: "secondary" })}>
                    Abrir la página ↗
                  </a>
                )}
                <Button
                  size="sm"
                  loading={busy === "sent"}
                  onClick={async () => {
                    const d = await run("sent", () => applyAgentApi.markSent(applicationId));
                    if (d) {
                      setDraft(d);
                      refreshWidgets();
                    }
                  }}
                >
                  Ya la envié
                </Button>
              </>
            ) : confirming ? (
              <Button size="sm" loading={busy === "submit" || busy === "save"} onClick={submit}>
                Confirmar envío a {company}
              </Button>
            ) : (
              <Button
                size="sm"
                disabled={!(puedeEnviar || (status === "needs_user" && dirty))}
                onClick={() => setConfirming(true)}
              >
                {status === "needs_user" && !dirty ? `Faltan ${pendientes || groups.pending.length}` : "Enviar"}
              </Button>
            )}
          </div>
        </div>
      )}

      {status === "submitted" && (
        <div className="rounded-2xl bg-emerald-50 p-4 text-sm text-emerald-900 ring-1 ring-inset ring-emerald-200 dark:bg-emerald-500/10 dark:text-emerald-200 dark:ring-emerald-500/25">
          Enviada{draft.submitted_at ? ` el ${new Date(draft.submitted_at).toLocaleString()}` : ""}. Ya figura como aplicada
          en tu <Link href="/applications" className="font-semibold underline">pipeline</Link>.
        </div>
      )}

      {(c.log ?? []).length > 0 && (
        <details className="text-xs text-gray-500 dark:text-gray-400">
          <summary className="cursor-pointer">Historial</summary>
          <ul className="mt-2 space-y-1">
            {(c.log ?? []).map((l) => (
              <li key={l.at + l.text}>
                {new Date(l.at).toLocaleString()} — {l.text}
              </li>
            ))}
          </ul>
        </details>
      )}
    </div>
  );
}

export default function ApplyReviewPage() {
  return (
    <RouteGuard>
      <ReviewContent />
    </RouteGuard>
  );
}
