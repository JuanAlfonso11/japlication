/** Makes crashes in the app visible instead of silent.
 *
 * The app runs mostly inside a WebView on a phone across Tailscale. When
 * something threw there, nothing was left behind: no console to open, no
 * log to read, and the user could only describe the symptom. This ships
 * those errors to the backend so they land in the same `error_logs` table
 * as server failures — one list, both sides.
 *
 * Two things it deliberately avoids doing:
 *
 * - **Reporting in a loop.** If the reporter itself throws, or the network
 *   is what's broken, retrying would generate an error per attempt forever.
 *   Failures to report are swallowed, and identical messages are collapsed.
 * - **Reporting noise.** A logged-out user hitting a 401, or a request
 *   cancelled by navigation, is the app working. Only genuine unhandled
 *   errors are sent.
 */

import { API_BASE_URL, getToken } from "@/lib/api";

/** The same message repeated is almost always one broken render looping,
 * not N distinct problems. Report each distinct one once per session. */
const reported = new Set<string>();

// A hard ceiling regardless of distinctness, so a component that throws
// with a unique message each frame (a timestamp, a random id) still can't
// flood the table.
const MAX_REPORTS_PER_SESSION = 20;
let reportCount = 0;

let installed = false;

function fingerprint(kind: string, message: string): string {
  return `${kind}::${message}`.slice(0, 300);
}

export async function reportClientError(
  error: unknown,
  context?: { kind?: string }
): Promise<void> {
  try {
    // Nothing to attach it to, and the endpoint requires auth — a crash on
    // the login screen simply isn't reportable, which is fine: those are
    // reproducible on a desktop where there IS a console.
    const token = getToken();
    if (!token) return;

    if (reportCount >= MAX_REPORTS_PER_SESSION) return;

    const err = error instanceof Error ? error : null;
    const kind = context?.kind ?? err?.name ?? "Error";
    const message = err?.message ?? String(error ?? "unknown error");

    const key = fingerprint(kind, message);
    if (reported.has(key)) return;
    reported.add(key);
    reportCount += 1;

    await fetch(`${API_BASE_URL}/system/client-errors`, {
      method: "POST",
      headers: {
        "Content-Type": "application/json",
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({
        kind: kind.slice(0, 200),
        message: message.slice(0, 2000),
        stack: err?.stack?.slice(0, 12000) ?? null,
        // Path only, never the query string — it can carry a shared job
        // URL or search terms, and those don't belong in a log. Mirrors
        // the same rule the backend follows.
        url: typeof window !== "undefined" ? window.location.pathname : null,
      }),
    });
  } catch {
    // The reporter must never be the thing that breaks the app, and a
    // failed report has nowhere useful to go anyway.
  }
}

/** Wires up the global handlers. Safe to call more than once. */
export function installErrorReporting(): void {
  if (installed || typeof window === "undefined") return;
  installed = true;

  window.addEventListener("error", (event) => {
    reportClientError(event.error ?? event.message, { kind: "WindowError" });
  });

  window.addEventListener("unhandledrejection", (event) => {
    reportClientError(event.reason, { kind: "UnhandledRejection" });
  });
}
