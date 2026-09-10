import { afterEach, describe, expect, it, vi } from "vitest";
import { openInOverleaf, __testing } from "./overleaf";

const { toTexFilename } = __testing;

/**
 * The contract these pin comes from https://www.overleaf.com/devs and was
 * confirmed from a real desktop browser. Getting a field name wrong here
 * fails in a particularly unhelpful way: Overleaf answers 200 with a
 * normal-looking page, so the user gets an empty editor rather than an error.
 *
 * Why these are unit tests and not a live check: Overleaf refuses scripted
 * requests to /docs wholesale. From a server, every variant — including a
 * POST with no fields at all, which should earn a different message —
 * returns the same "There was an error creating your project". A script
 * that sees that page has learned nothing about whether the integration
 * works, so the only real verification is a person clicking the button in
 * a browser. Do not "fix" that by adding an automated check against the
 * live endpoint: it will fail forever and prove nothing.
 */

describe("toTexFilename", () => {
  it("keeps a readable name and adds the .tex extension", () => {
    expect(toTexFilename("CV - Backend Engineer")).toBe("CV - Backend Engineer.tex");
  });

  it("strips characters that are not valid in a filename", () => {
    // Job titles routinely carry slashes and colons: "Software Developer
    // C#/.NET (4 openings)" is a real posting in this database.
    expect(toTexFilename("Dev C#/.NET: 50% remote")).toBe("Dev C#-.NET- 50- remote.tex");
  });

  it("falls back rather than producing a file called '.tex'", () => {
    expect(toTexFilename("   ")).toBe("cv.tex");
    expect(toTexFilename("")).toBe("cv.tex");
  });

  it("caps the length so a long job title cannot make an unusable name", () => {
    const name = toTexFilename("x".repeat(300));
    expect(name.length).toBeLessThanOrEqual(84);
    expect(name.endsWith(".tex")).toBe(true);
  });
});

describe("openInOverleaf", () => {
  afterEach(() => {
    vi.restoreAllMocks();
    document.querySelectorAll("form").forEach((f) => f.remove());
  });

  it("posts the documented fields to the documented endpoint", () => {
    let captured: HTMLFormElement | null = null;
    vi.spyOn(HTMLFormElement.prototype, "submit").mockImplementation(function (
      this: HTMLFormElement
    ) {
      // Read the form while it is still attached — the caller removes it
      // immediately after submitting.
      captured = this;
      const fields: Record<string, string> = {};
      this.querySelectorAll("input").forEach((i) => {
        fields[i.name] = i.value;
      });
      expect(this.method.toLowerCase()).toBe("post");
      expect(this.action).toBe("https://www.overleaf.com/docs");
      expect(this.target).toBe("_blank");
      expect(fields.snip).toContain("\\documentclass");
      expect(fields.snip_name).toBe("CV - Dev.tex");
      // One of Overleaf's four documented engines, and the one the template
      // is written for.
      expect(fields.engine).toBe("pdflatex");
    });

    openInOverleaf("\\documentclass{article}\\begin{document}hi\\end{document}", "CV - Dev");
    expect(captured).not.toBeNull();
  });

  it("leaves no stray form behind in the page", () => {
    vi.spyOn(HTMLFormElement.prototype, "submit").mockImplementation(() => {});
    openInOverleaf("\\documentclass{article}", "CV");
    expect(document.querySelectorAll("form").length).toBe(0);
  });
});
