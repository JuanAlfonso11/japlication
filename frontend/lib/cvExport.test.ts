import { afterEach, describe, expect, it, vi } from "vitest";

vi.mock("./platform", () => ({ isNativeApp: vi.fn(() => false) }));
vi.mock("./overleaf", () => ({ openInOverleaf: vi.fn() }));

import type { DownloadOutcome } from "./api";
import { describeSave, exportLatex, safeFilename } from "./cvExport";
import { openInOverleaf } from "./overleaf";
import { isNativeApp } from "./platform";

describe("safeFilename", () => {
  it("replaces characters phones and Windows refuse in a filename", () => {
    expect(safeFilename("Dev C#/.NET: remote")).toBe("Dev C#-.NET- remote");
  });

  it("collapses stray whitespace", () => {
    expect(safeFilename("  CV   (EN) ")).toBe("CV (EN)");
  });
});

describe("describeSave", () => {
  it("says nothing in a browser, which has its own downloads UI", () => {
    expect(describeSave(null, "PDF")).toBeNull();
  });

  it("names the folder when the file landed in Documents", () => {
    expect(describeSave({ savedTo: "Documentos/JobPilot" }, "PDF")).toBe(
      "PDF guardado en Documentos/JobPilot"
    );
  });

  it("asks the user to pick a place when it fell back to sharing", () => {
    expect(describeSave({ shared: true }, "PDF")).toBe("PDF listo — elige dónde guardarlo");
  });
});

describe("exportLatex", () => {
  afterEach(() => {
    vi.clearAllMocks();
  });

  it("opens Overleaf in a browser and downloads nothing", async () => {
    vi.mocked(isNativeApp).mockReturnValue(false);
    const download = vi.fn(async (_filename: string): Promise<DownloadOutcome> => null);

    const notice = await exportLatex({
      label: "CV (EN)",
      getSource: async () => "\\documentclass{article}",
      download,
    });

    expect(openInOverleaf).toHaveBeenCalledWith("\\documentclass{article}", "CV (EN)");
    expect(download).not.toHaveBeenCalled();
    expect(notice).toBeNull();
  });

  it("saves the .tex on a phone, where the Overleaf POST cannot survive", async () => {
    vi.mocked(isNativeApp).mockReturnValue(true);
    const getSource = vi.fn(async () => "never fetched");
    const download = vi.fn(
      async (_filename: string): Promise<DownloadOutcome> => ({ savedTo: "Documentos/JobPilot" })
    );

    const notice = await exportLatex({ label: "CV: Juan (ES)", getSource, download });

    expect(download).toHaveBeenCalledWith("CV- Juan (ES).tex");
    expect(getSource).not.toHaveBeenCalled();
    expect(openInOverleaf).not.toHaveBeenCalled();
    expect(notice).toBe("Archivo .tex guardado en Documentos/JobPilot");
  });
});
