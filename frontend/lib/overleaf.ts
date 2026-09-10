/**
 * Opens a LaTeX document in Overleaf.
 *
 * Overleaf has no public compile API — nothing here can ask it for a PDF.
 * What it does document is an endpoint that accepts a source document and
 * opens it as a new project, already compiling. That is a browser
 * navigation, not a server call, which is also the only shape that could
 * work here: this backend lives behind Tailscale, so Overleaf's other
 * option (`snip_uri`, where Overleaf fetches a URL itself) could never
 * reach it.
 *
 * A hidden auto-submitting form rather than `fetch`: the response is a
 * whole Overleaf page meant for the user, and a cross-origin POST made
 * with fetch could neither read it nor navigate to it.
 */

const OVERLEAF_ENDPOINT = "https://www.overleaf.com/docs";

export function openInOverleaf(source: string, projectName: string): void {
  const form = document.createElement("form");
  form.method = "POST";
  form.action = OVERLEAF_ENDPOINT;
  // A new tab, so the user does not lose the job they were looking at.
  form.target = "_blank";
  // The form posts to another origin and carries only what the user chose
  // to send; no referrer needs to travel with it.
  form.rel = "noopener noreferrer";
  form.style.display = "none";

  const fields: Record<string, string> = {
    snip: source,
    snip_name: projectName,
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
