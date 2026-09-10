import type { DownloadOutcome } from "./api";
import { openInOverleaf } from "./overleaf";
import { isNativeApp } from "./platform";

/**
 * Shared behaviour of the CV download buttons, used by both the tailored CV
 * on a job and the master CV on the profile. Kept in one place because each
 * piece encodes a platform difference that failed silently the first time:
 * a phone announces no downloads, and Overleaf cannot be opened from one.
 */

/** Replaces the characters Windows and Android refuse in a filename. Job
 * titles routinely contain them: "Software Developer C#/.NET (4 openings)"
 * is a real posting in this database. */
export function safeFilename(name: string): string {
  return name.replace(/[/\\?%*:|"<>]/g, "-").replace(/\s+/g, " ").trim();
}

/** Turns "where did the file go" into something worth showing. Silent in a
 * browser, which already has its own downloads UI; a phone has none. */
export function describeSave(outcome: DownloadOutcome, what: string): string | null {
  if (!outcome) return null;
  if ("savedTo" in outcome) return `${what} guardado en ${outcome.savedTo}`;
  return `${what} listo — elige dónde guardarlo`;
}

/**
 * The LaTeX button.
 *
 * In a browser it opens Overleaf with the source already compiling. Inside
 * the Android app it saves the .tex instead: Overleaf takes the source in a
 * POST body, and the WebView hands a `target=_blank` navigation to the
 * system browser with only a URL, so the body is lost and Overleaf answers
 * "missing some required parameters" — reported from a real phone. Saving
 * the file is also the honest flow there, since Overleaf's editor is
 * unusable on a phone.
 *
 * Returns the notice to show, or null when Overleaf opened in a new tab.
 */
export async function exportLatex(options: {
  label: string;
  getSource: () => Promise<string>;
  download: (filename: string) => Promise<DownloadOutcome>;
}): Promise<string | null> {
  if (isNativeApp()) {
    const outcome = await options.download(`${safeFilename(options.label)}.tex`);
    return describeSave(outcome, "Archivo .tex");
  }
  openInOverleaf(await options.getSource(), options.label);
  return null;
}
