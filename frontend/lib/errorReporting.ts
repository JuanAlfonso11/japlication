/** Turns crashes into a "Reportar el fallo" prompt instead of silence.
 *
 * The app runs mostly inside a WebView on a phone. When something threw
 * there, nothing was left behind: no console to open, no log to read. A
 * crash is captured here and CrashReportDialog asks the user whether to
 * send it; only then does it land in the backend's `error_logs` table
 * (which only the admin can read), with the user's own note attached.
 *
 * Two things it deliberately avoids doing:
 *
 * - **Prompting in a loop.** One prompt at a time, each distinct error at
 *   most once per session, and a hard ceiling on top. A failed send is
 *   swallowed rather than retried.
 * - **Prompting for noise.** A logged-out user hitting a 401, or a request
 *   cancelled by navigation, is the app working. Only genuine unhandled
 *   errors are captured.
 */

import { API_BASE_URL, getToken } from "@/lib/api";

/** The same message repeated is almost always one broken render looping,
 * not N distinct problems. Prompt for each distinct one once per session. */
const seen = new Set<string>();

// A hard ceiling regardless of distinctness, so a component that throws
// with a unique message each frame (a timestamp, a random id) still can't
// keep the prompt coming back.
const MAX_CAPTURES_PER_SESSION = 20;
let captureCount = 0;

let installed = false;

export type PendingReport = {
  kind: string;
  message: string;
  stack: string | null;
  url: string | null;
};

let pending: PendingReport | null = null;
const listeners = new Set<() => void>();

function setPending(next: PendingReport | null) {
  pending = next;
  listeners.forEach((l) => l());
}

export function subscribeToPendingReport(listener: () => void): () => void {
  listeners.add(listener);
  return () => listeners.delete(listener);
}

export function getPendingReport(): PendingReport | null {
  return pending;
}

function fingerprint(kind: string, message: string): string {
  return `${kind}::${message}`.slice(0, 300);
}

/** Holds the error for the "Reportar el fallo" prompt. Nothing is sent. */
export function captureClientError(error: unknown, context?: { kind?: string }): void {
  try {
    // The report endpoint requires a session — a crash on the login screen
    // isn't reportable, and prompting for it would only lead to a failure.
    if (!getToken()) return;
    // One prompt at a time; a second error while it's open is almost
    // always a consequence of the first.
    if (pending) return;
    if (captureCount >= MAX_CAPTURES_PER_SESSION) return;

    const err = error instanceof Error ? error : null;
    const kind = context?.kind ?? err?.name ?? "Error";
    const message = err?.message ?? String(error ?? "unknown error");

    const key = fingerprint(kind, message);
    if (seen.has(key)) return;
    seen.add(key);
    captureCount += 1;

    setPending({
      kind: kind.slice(0, 200),
      message,
      stack: err?.stack?.slice(0, 12000) ?? null,
      // Path only, never the query string — it can carry a shared job
      // URL or search terms, and those don't belong in a log. Mirrors
      // the same rule the backend follows.
      url: typeof window !== "undefined" ? window.location.pathname : null,
    });
  } catch {
    // The reporter must never be the thing that breaks the app.
  }
}

export function dismissPendingReport(): void {
  setPending(null);
}

/** Sends the captured error, with the user's note on top when there is one. */
export async function sendPendingReport(note: string): Promise<void> {
  const report = pending;
  setPending(null);
  const token = getToken();
  if (!report || !token) return;
  const trimmed = note.trim();
  const message = trimmed ? `Comentario del usuario: ${trimmed}

${report.message}` : report.message;
  try {
    await fetch(`${API_BASE_URL}/system/client-errors`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ ...report, message: message.slice(0, 2000) }),
    });
  } catch {
    // A failed report has nowhere useful to go.
  }
}

/** Wires up the global handlers. Safe to call more than once. */
export function installErrorReporting(): void {
  if (installed || typeof window === "undefined") return;
  installed = true;

  window.addEventListener("error", (event) => {
    captureClientError(event.error ?? event.message, { kind: "WindowError" });
  });

  window.addEventListener("unhandledrejection", (event) => {
    captureClientError(event.reason, { kind: "UnhandledRejection" });
  });
}
