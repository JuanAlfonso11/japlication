import type { ApplicationDraft, ApplicationDraftListItem, ApplyMode, DraftField, DraftStatus } from "./types";

/** "Aplicar al deslizar": cómo se cuenta cada estado de una aplicación en
 * curso. Un solo sitio para Inicio, la bandeja y la revisión, para que la
 * misma aplicación no se llame de tres formas distintas. */

export const MODE_LABELS: Record<ApplyMode, { title: string; body: string }> = {
  save: {
    title: "Solo guardar",
    body: "La derecha guarda la vacante en tu pipeline. Aplicas tú, cuando quieras.",
  },
  review: {
    title: "Preparar y revisar",
    body: "La derecha prepara la aplicación (CV a medida, carta, formulario) y te la deja lista. Sale cuando tú tocas Enviar.",
  },
  auto: {
    title: "Aplicar automáticamente",
    body: "Si no falta nada y nada pide revisión, sale sola unos minutos después del swipe, y puedes deshacerla hasta entonces. Si algo pide revisión, espera por ti.",
  },
};

export const DRAFT_STATUS_LABELS: Record<DraftStatus, string> = {
  preparing: "Preparando",
  needs_user: "Te falta responder",
  ready: "Lista para enviar",
  scheduled: "Sale sola pronto",
  submitting: "Enviando",
  submitted: "Enviada",
  handoff: "Envíala tú",
  failed: "No se pudo preparar",
  cancelled: "Descartada",
  approved: "Aprobada",
};

export type DraftTone = "busy" | "action" | "ok" | "wait" | "bad" | "muted";

export const DRAFT_STATUS_TONE: Record<DraftStatus, DraftTone> = {
  preparing: "busy",
  submitting: "busy",
  needs_user: "action",
  handoff: "action",
  ready: "action",
  scheduled: "wait",
  submitted: "ok",
  approved: "ok",
  failed: "bad",
  cancelled: "muted",
};

export const TONE_CLASSES: Record<DraftTone, string> = {
  busy: "bg-gray-100 text-gray-700 ring-gray-200 dark:bg-gray-800 dark:text-gray-200 dark:ring-gray-700",
  action: "bg-amber-50 text-amber-800 ring-amber-100 dark:bg-amber-500/10 dark:text-amber-300 dark:ring-amber-500/20",
  wait: "bg-brand-50 text-brand-700 ring-brand-100 dark:bg-brand-500/15 dark:text-brand-300 dark:ring-brand-500/20",
  ok: "bg-emerald-50 text-emerald-700 ring-emerald-100 dark:bg-emerald-500/10 dark:text-emerald-300 dark:ring-emerald-500/20",
  bad: "bg-rose-50 text-rose-700 ring-rose-100 dark:bg-rose-500/10 dark:text-rose-300 dark:ring-rose-500/20",
  muted: "bg-gray-50 text-gray-500 ring-gray-200 dark:bg-gray-900 dark:text-gray-400 dark:ring-gray-800",
};

/** Mientras está en uno de estos, la pantalla vuelve a preguntar. */
export function isMoving(status: DraftStatus): boolean {
  return status === "preparing" || status === "submitting";
}

/** Una línea que dice qué pasa y qué hace falta. */
export function describeDraft(
  d: Pick<ApplicationDraftListItem, "status" | "pending_count" | "handoff_reason" | "error" | "scheduled_for" | "channel">,
  now: Date = new Date()
): string {
  switch (d.status) {
    case "preparing":
      return "Adaptando tu CV y llenando el formulario…";
    case "needs_user": {
      const n = d.pending_count || 1;
      return `Falta${n === 1 ? "" : "n"} ${n} respuesta${n === 1 ? "" : "s"} que solo tú puedes dar.`;
    }
    case "ready":
      return d.channel === "email" ? "El correo está listo. Revísalo y envíalo." : "Todo respondido. Revísala y envíala.";
    case "scheduled":
      return `Sale sola ${minutesFrom(d.scheduled_for, now)}. Puedes deshacerla hasta entonces.`;
    case "submitting":
      return "Enviando…";
    case "submitted":
      return "Enviada. Ya está en tu pipeline como aplicada.";
    case "handoff":
      return d.handoff_reason || "Tu CV y tus respuestas están listos: envíala en la página de la empresa.";
    case "failed":
      return d.error || "No se pudo preparar.";
    case "cancelled":
      return "La descartaste. La vacante sigue guardada.";
    default:
      return "";
  }
}

export function minutesFrom(iso: string | null | undefined, now: Date = new Date()): string {
  if (!iso) return "en unos minutos";
  const ms = new Date(iso).getTime() - now.getTime();
  if (ms <= 30_000) return "ahora";
  const min = Math.ceil(ms / 60_000);
  return `en ${min} min`;
}

/** Los campos que el usuario tiene que mirar primero: los obligatorios sin
 * responder, luego lo que respondió la IA (él lo firma), y lo demás. */
export function groupFields(fields: DraftField[] = []): {
  pending: DraftField[];
  byAi: DraftField[];
  filled: DraftField[];
  skipped: DraftField[];
} {
  const pending: DraftField[] = [];
  const byAi: DraftField[] = [];
  const filled: DraftField[] = [];
  const skipped: DraftField[] = [];
  for (const f of fields) {
    if (f.status === "needs_user" || (f.required && f.status !== "filled")) pending.push(f);
    else if (f.status === "filled" && f.source === "ai") byAi.push(f);
    else if (f.status === "filled") filled.push(f);
    else skipped.push(f);
  }
  return { pending, byAi, filled, skipped };
}

/** Qué botón principal tiene la revisión. */
export function primaryAction(draft: Pick<ApplicationDraft, "status" | "channel" | "content">):
  | "answer"
  | "submit"
  | "open_site"
  | "none" {
  if (draft.status === "needs_user") return "answer";
  if (draft.status === "ready" || draft.status === "scheduled") return "submit";
  if (draft.status === "handoff") return "open_site";
  return "none";
}

export const SOURCE_LABELS: Record<string, string> = {
  profile: "De tu perfil",
  screening: "Tu respuesta guardada",
  ai: "Redactada por la IA",
  user: "Tu respuesta",
};
