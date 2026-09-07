/** Pulls the job URL out of whatever another app handed us.
 *
 * Android's share sheet delivers one blob of text, and apps put wildly
 * different things in it. Chrome sends the bare URL; LinkedIn and WhatsApp
 * wrap it in prose ("Mira esta vacante: https://…"); some apps send the
 * page title on one line and the URL on the next. So the share target can't
 * assume it received a URL — it has to go looking for one.
 */

// Deliberately not a "validate a URL" regex (those are famously wrong and
// long). This only has to *locate* a plausible http(s) URL inside free text;
// `new URL()` below does the actual validating.
const URL_IN_TEXT = /https?:\/\/[^\s<>"')\]]+/gi;

// Trailing punctuation that belongs to the sentence, not the URL — "…mira
// esto: https://x.com/job." should not import a URL ending in a period.
const TRAILING_JUNK = /[.,;:!?)\]}'"]+$/;

export function extractSharedUrl(text: string | null | undefined): string | null {
  if (!text) return null;

  const matches = text.match(URL_IN_TEXT);
  if (!matches) return null;

  for (const raw of matches) {
    const candidate = raw.replace(TRAILING_JUNK, "");
    try {
      const parsed = new URL(candidate);
      if (parsed.protocol === "http:" || parsed.protocol === "https:") {
        return parsed.toString();
      }
    } catch {
      // Not parseable — try the next match rather than giving up, since a
      // share can contain several links (e.g. a signature).
    }
  }

  return null;
}

/** True when the shared text was *only* a URL, with nothing else around it.
 * Used to decide whether the leftover prose is worth keeping as a note. */
export function isBareUrl(text: string | null | undefined): boolean {
  if (!text) return false;
  const trimmed = text.trim();
  const url = extractSharedUrl(trimmed);
  return url !== null && trimmed.replace(TRAILING_JUNK, "") === url.replace(/\/$/, "");
}
