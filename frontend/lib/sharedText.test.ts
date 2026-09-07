import { describe, expect, it } from "vitest";
import { extractSharedUrl } from "./sharedText";

describe("extractSharedUrl", () => {
  it("takes a bare URL as-is (what Chrome sends)", () => {
    expect(extractSharedUrl("https://empresa.com/careers/senior-engineer")).toBe(
      "https://empresa.com/careers/senior-engineer"
    );
  });

  it("finds the URL inside prose (what LinkedIn and WhatsApp send)", () => {
    expect(
      extractSharedUrl("Mira esta vacante: https://empresa.com/jobs/42 me parece ideal para ti")
    ).toBe("https://empresa.com/jobs/42");
  });

  it("handles the title-on-one-line, URL-on-the-next shape", () => {
    expect(extractSharedUrl("Senior Backend Engineer at Acme\nhttps://acme.com/jobs/7")).toBe(
      "https://acme.com/jobs/7"
    );
  });

  it("drops sentence punctuation that isn't part of the link", () => {
    expect(extractSharedUrl("Postúlate acá: https://acme.com/jobs/7.")).toBe(
      "https://acme.com/jobs/7"
    );
    expect(extractSharedUrl("(https://acme.com/jobs/7)")).toBe("https://acme.com/jobs/7");
  });

  it("keeps query strings, which job boards depend on", () => {
    expect(extractSharedUrl("https://boards.greenhouse.io/acme?gh_jid=123")).toBe(
      "https://boards.greenhouse.io/acme?gh_jid=123"
    );
  });

  it("returns null when there's no link at all", () => {
    expect(extractSharedUrl("Buscan un backend senior, escribile a Ana")).toBeNull();
    expect(extractSharedUrl("")).toBeNull();
    expect(extractSharedUrl(null)).toBeNull();
    expect(extractSharedUrl(undefined)).toBeNull();
  });

  it("ignores non-http schemes", () => {
    expect(extractSharedUrl("mailto:rrhh@acme.com")).toBeNull();
    expect(extractSharedUrl("Escribe a rrhh@acme.com")).toBeNull();
  });

  it("takes the first usable link when several are shared", () => {
    expect(
      extractSharedUrl("https://acme.com/jobs/7 y tambien https://otra.com/jobs/9")
    ).toBe("https://acme.com/jobs/7");
  });
});
