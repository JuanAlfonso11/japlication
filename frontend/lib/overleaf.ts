/**
 * Opens a LaTeX document in Overleaf.
 *
 * Contract per https://www.overleaf.com/devs (checked 2026-09-10), confirmed
 * working from a real desktop browser with a generated CV on the same day:
 *
 *   endpoint  https://www.overleaf.com/docs, POST
 *   snip      the raw LaTeX source
 *   snip_name the FILE name it is saved under (not a project title)
 *   engine    one of latex_dvipdf | pdflatex | xelatex | lualatex
 *
 * Overleaf has no public compile API, so nothing here can ask it for a
 * PDF. Its other input, `snip_uri`, has Overleaf fetch a URL itself — "the
 * file must be accessible from our servers", which this backend never is:
 * it lives behind Tailscale. `snip` carrying the source in the request body
 * is the only option that works, and a form POST is the only way to do that
 * and still land the user on the resulting page.
 *
 * A hidden auto-submitting form rather than `fetch`: the response is a
 * whole Overleaf page meant for the user, and a cross-origin POST made with
 * fetch could neither read it nor navigate to it.
 *
 * Two documented behaviours worth knowing, neither of which bites us:
 * Windows newlines are converted to unix ones (the generator emits \n
 * anyway), and source with no \documentclass is auto-wrapped in a default
 * document — ours declares one, so Overleaf compiles exactly what was sent.
 *
 * `visual_editor` is deliberately not set. The template defines its own
 * macros (\rolehead, \rolemeta) and the Visual Editor renders unknown
 * macros poorly; the Code Editor default shows the real source.
 */

const OVERLEAF_ENDPOINT = "https://www.overleaf.com/docs";

/** `snip_name` names a file, so it has to be a valid one: no slashes, no
 * characters Windows rejects, and a .tex extension so Overleaf treats it as
 * the main document rather than an unknown attachment. */
function toTexFilename(label: string): string {
  const safe = label
    .replace(/[/\\?%*:|"<>]/g, "-")
    .replace(/\s+/g, " ")
    .trim()
    .slice(0, 80);
  return `${safe || "cv"}.tex`;
}

export function openInOverleaf(source: string, documentLabel: string): void {
  const form = document.createElement("form");
  form.method = "POST";
  form.action = OVERLEAF_ENDPOINT;
  // A new tab, so the user does not lose the job they were looking at.
  form.target = "_blank";
  form.rel = "noopener noreferrer";
  form.style.display = "none";

  const fields: Record<string, string> = {
    snip: source,
    snip_name: toTexFilename(documentLabel),
    // The template sticks to pdflatex-safe packages on purpose — see
    // backend/app/services/resume_latex.py.
    engine: "pdflatex",
  };

  for (const [name, value] of Object.entries(fields)) {
    const input = document.createElement("input");
    input.type = "hidden";
    input.name = name;
    input.value = value;
    form.appendChild(input);
  }

  document.body.appendChild(form);
  form.submit();
  form.remove();
}

export const __testing = { toTexFilename };
