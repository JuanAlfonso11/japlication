/** Datos de los widgets de Android ("Próxima vacante" y "Tu pipeline").
 *
 * Un widget de pantalla de inicio no puede ejecutar la app: Android dibuja
 * RemoteViews desde un proceso aparte, sin WebView y sin la sesión (que vive
 * en localStorage). Dos cosas lo resuelven, ambas por el plugin nativo
 * `JobPilotWidgets` (WidgetBridgePlugin.java):
 *
 * 1. La "foto" de lo que se ve: la app se la pasa al cargar Home, después de
 *    cada swipe o deshacer, al cambiar el estado de una postulación, y al
 *    entrar o salir de la app (WidgetSync.tsx).
 * 2. Una credencial propia del widget (`linkWidget`), que solo abre
 *    /widget/* en el backend: con ella ✕ / ✓ / Deshacer deciden desde la
 *    pantalla de inicio sin abrir la app, y el widget se refresca solo.
 *    Nunca se le pasa la sesión de la app. Al cerrar sesión se revoca.
 *
 * Fuera de la app nativa (pestaña de navegador) todo esto no hace nada, y en
 * un APK viejo sin el plugin (o sin `link`) la llamada falla en silencio.
 */

import { registerPlugin } from "@capacitor/core";
import { API_BASE_URL, applicationsApi, jobsApi, widgetApi } from "@/lib/api";
import { isNativeApp } from "@/lib/platform";
import type { Application, Job } from "@/lib/types";

export const WIDGET_PAYLOAD_VERSION = 1;

/** Lo mismo que cuenta la fila de chips de Home: aplicadas, entrevistas y
 * ofertas. "Guardadas" no va: un swipe a la derecha ya la cuenta la cola al
 * bajar, y cuatro cifras es lo que cabe legible en un widget de 4x1. */
export const PIPELINE_WIDGET_STATUSES = ["applied", "interviewing", "offer"] as const;

export interface WidgetNextJob {
  id: string;
  title: string;
  company: string;
  /** "Remoto", "Híbrido · Madrid", "Santiago"... ya listo para mostrar. */
  place: string;
  /** 0-100, o null si todavía no hay match calculado. */
  score: number | null;
}

export interface WidgetPayload {
  v: number;
  /** Epoch en ms. El widget lo usa para decir "hace cuánto" si los datos son viejos. */
  updatedAt: number;
  queueCount: number;
  next: WidgetNextJob | null;
  /** Las que van detrás de `next`. El widget avanza a la siguiente al
   * instante al pasar o guardar, sin esperar a la red. */
  upcoming: WidgetNextJob[];
  pipeline: { applied: number; interviewing: number; offer: number };
}

/** Cuántas tarjetas de reserva lleva la foto (igual que UPCOMING en el router). */
export const WIDGET_UPCOMING = 5;

interface WidgetsPlugin {
  update(options: { data: string }): Promise<void>;
  clear(): Promise<void>;
  status(): Promise<{ linked: boolean; userId: string | null; deviceId: string }>;
  link(options: { token: string; apiBase: string; userId: string }): Promise<void>;
}

const Widgets = registerPlugin<WidgetsPlugin>("JobPilotWidgets");

const MAX_TEXT = 140;

function clip(text: string | null | undefined): string {
  const clean = (text ?? "").replace(/\s+/g, " ").trim();
  return clean.length > MAX_TEXT ? `${clean.slice(0, MAX_TEXT - 1)}…` : clean;
}

const REMOTE_LABELS: Record<string, string> = {
  remote: "Remoto",
  hybrid: "Híbrido",
  onsite: "Presencial",
};

export function describePlace(job: Pick<Job, "location" | "remote_type">): string {
  const mode = job.remote_type ? REMOTE_LABELS[job.remote_type] : undefined;
  const location = clip(job.location);
  if (mode === "Remoto") return location && !/remot/i.test(location) ? `Remoto · ${location}` : "Remoto";
  if (mode && location) return `${mode} · ${location}`;
  return mode ?? location;
}

export function toWidgetJob(job: Job): WidgetNextJob {
  const score = job.match?.overall_score;
  return {
    id: job.id,
    title: clip(job.title) || "Vacante",
    company: clip(job.company),
    place: describePlace(job),
    score: typeof score === "number" ? Math.max(0, Math.min(100, Math.round(score))) : null,
  };
}

export function countPipeline(applications: Pick<Application, "status">[]): WidgetPayload["pipeline"] {
  const counts = { applied: 0, interviewing: 0, offer: 0 };
  for (const a of applications) {
    if (a.status === "applied" || a.status === "interviewing" || a.status === "offer") counts[a.status] += 1;
  }
  return counts;
}

export function buildWidgetPayload(input: {
  queueCount: number;
  next: Job | null;
  upcoming?: Job[];
  pipeline: WidgetPayload["pipeline"];
  now?: number;
}): WidgetPayload {
  return {
    v: WIDGET_PAYLOAD_VERSION,
    updatedAt: input.now ?? Date.now(),
    queueCount: Math.max(0, Math.floor(input.queueCount)),
    next: input.next ? toWidgetJob(input.next) : null,
    upcoming: input.next ? (input.upcoming ?? []).slice(0, WIDGET_UPCOMING).map(toWidgetJob) : [],
    pipeline: input.pipeline,
  };
}

/** Le pasa los datos al widget. Nunca lanza: un widget desactualizado no
 * puede romper nada de la app. */
export async function pushWidgets(payload: WidgetPayload): Promise<void> {
  if (!isNativeApp()) return;
  try {
    await Widgets.update({ data: JSON.stringify(payload) });
  } catch {
    // APK anterior a los widgets, o el usuario no tiene ninguno puesto.
  }
}

/** Al cerrar sesión: el lado nativo revoca la credencial del widget en el
 * servidor (con la propia credencial, la sesión ya no existe) y borra todo. */
export async function clearWidgets(): Promise<void> {
  if (!isNativeApp()) return;
  try {
    await Widgets.clear();
  } catch {
    // Igual que arriba.
  }
}

/** Pide al backend solo lo que el widget enseña: la primera vacante de la
 * cola (ya viene ordenada por match) y tres totales. Cuatro peticiones
 * pequeñas en vez de bajar las 200 postulaciones como hace Home. */
export async function fetchWidgetPayload(): Promise<WidgetPayload> {
  const [matches, ...byStatus] = await Promise.all([
    jobsApi.matches({ limit: WIDGET_UPCOMING + 1 }),
    ...PIPELINE_WIDGET_STATUSES.map((status) => applicationsApi.list(status, 1, 0)),
  ]);
  const total = (i: number) => byStatus[i]?.total ?? 0;
  return buildWidgetPayload({
    queueCount: matches.total,
    next: matches.items[0] ?? null,
    upcoming: matches.items.slice(1),
    pipeline: { applied: total(0), interviewing: total(1), offer: total(2) },
  });
}

/** Le da al widget su propia credencial (si aún no la tiene, o si la tiene
 * de otra cuenta que usó este teléfono), para que pase y guarde sin abrir
 * la app. Nunca lanza: sin credencial, ✕ / ✓ siguen abriendo la app. */
export async function linkWidget(userId: string): Promise<void> {
  if (!isNativeApp() || !userId) return;
  try {
    const status = await Widgets.status();
    if (status.linked && status.userId === userId) return;
    const { token } = await widgetApi.issueToken(status.deviceId);
    await Widgets.link({ token, apiBase: API_BASE_URL, userId });
  } catch {
    // APK anterior a esta función, o sin red: se vuelve a intentar al
    // próximo arranque.
  }
}

let lastRefresh = 0;
let inFlight: Promise<void> | null = null;

/** Refresco desde el servidor, con un mínimo de `minIntervalMs` entre uno y
 * otro para que entrar y salir de la app varias veces seguidas no dispare
 * una ráfaga de peticiones. */
export function refreshWidgets(minIntervalMs = 30_000): Promise<void> {
  if (!isNativeApp()) return Promise.resolve();
  if (inFlight) return inFlight;
  if (Date.now() - lastRefresh < minIntervalMs) return Promise.resolve();
  inFlight = fetchWidgetPayload()
    .then(pushWidgets)
    .catch(() => {
      // Sin red o sesión caducada: el widget se queda con la última foto.
    })
    .finally(() => {
      lastRefresh = Date.now();
      inFlight = null;
    });
  return inFlight;
}

/** Marca los datos como recién enviados, para que el refresco por entrar o
 * salir de la app no repita justo lo que Home acaba de mandar. */
export function markWidgetsFresh(): void {
  lastRefresh = Date.now();
}

/** Lo que pide un toque en ✕ o ✓ del widget: `/?swipe=right&job=<id>`.
 * Devuelve null si la URL no trae una intención válida. */
export function parseSwipeIntent(search: string): { decision: "left" | "right"; jobId: string } | null {
  const params = new URLSearchParams(search);
  const decision = params.get("swipe");
  const jobId = params.get("job");
  if ((decision !== "left" && decision !== "right") || !jobId) return null;
  if (!/^[A-Za-z0-9-]{1,64}$/.test(jobId)) return null;
  return { decision, jobId };
}
