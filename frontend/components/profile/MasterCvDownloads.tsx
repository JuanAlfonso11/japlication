"use client";

import { useEffect, useState } from "react";
import { ApiError, profileApi } from "@/lib/api";
import { describeSave, exportLatex, safeFilename } from "@/lib/cvExport";
import { isNativeApp } from "@/lib/platform";
import type { ProfileLanguage } from "@/lib/types";

type Format = "pdf" | "tex" | "txt";

/**
 * Download buttons for the master CV — the whole profile rendered like a
 * tailored CV, in the language the CV tab is currently showing.
 *
 * The server renders what is SAVED. With unsaved edits in the form, a
 * download would silently be the previous version — the one mistake here
 * nobody notices until the file has been sent — so the parent passes a
 * `blockedReason` and the buttons stay disabled until the profile is saved.
 */
export default function MasterCvDownloads({
  language,
  fullName,
  blockedReason,
}: {
  language: ProfileLanguage;
  fullName?: string | null;
  blockedReason?: string | null;
}) {
  const [busy, setBusy] = useState<Format | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  // Read after mount: the server render has no window, so reading it during
  // render would disagree with the first client render.
  const [nativeApp, setNativeApp] = useState(false);
  useEffect(() => setNativeApp(isNativeApp()), []);

  // A notice about the English file is wrong once the Spanish tab is showing.
  useEffect(() => {
    setNotice(null);
    setError(null);
  }, [language]);

  // This is what a recruiter sees when the file is attached to an
  // application, so it carries the person's name rather than anything
  // internal like "cv-maestro".
  const baseName = safeFilename(
    `CV${fullName ? ` - ${fullName}` : ""} (${language.toUpperCase()})`
  );

  async function run(format: Format, action: () => Promise<string | null>) {
    setBusy(format);
    setNotice(null);
    setError(null);
    try {
      setNotice(await action());
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo descargar el CV maestro.");
    } finally {
      setBusy(null);
    }
  }

  const disabled = busy !== null || Boolean(blockedReason);
  const secondaryButton =
    "rounded-lg border border-gray-200 px-3 py-1.5 text-xs font-semibold text-gray-600 hover:bg-gray-50 disabled:cursor-not-allowed disabled:opacity-60 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800";

  return (
    <div className="rounded-xl border border-gray-200 bg-white p-3 dark:border-gray-800 dark:bg-gray-900">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div className="min-w-0">
          <p className="text-sm font-semibold text-gray-900 dark:text-gray-100">Descargar CV maestro</p>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            {blockedReason ??
              `Tu perfil completo en ${language === "es" ? "español" : "inglés"}, con el mismo formato que los CVs por vacante.`}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button
            type="button"
            disabled={disabled}
            onClick={() =>
              run("pdf", async () =>
                describeSave(await profileApi.downloadMasterPdf(language, `${baseName}.pdf`), "PDF")
              )
            }
            className="rounded-lg bg-brand-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {busy === "pdf" ? "Generando…" : "PDF"}
          </button>
          <button
            type="button"
            disabled={disabled}
            title={
              nativeApp
                ? "Guarda el CV en LaTeX (.tex) para abrirlo en Overleaf desde una computadora"
                : "Abre el CV en Overleaf como documento LaTeX, ya compilando"
            }
            onClick={() =>
              run("tex", () =>
                exportLatex({
                  label: baseName,
                  getSource: () => profileApi.masterLatexSource(language),
                  download: (filename) => profileApi.downloadMasterTex(language, filename),
                })
              )
            }
            className={secondaryButton}
          >
            {busy === "tex"
              ? nativeApp
                ? "Guardando…"
                : "Abriendo…"
              : nativeApp
                ? "Guardar .tex"
                : "LaTeX (Overleaf)"}
          </button>
          <button
            type="button"
            disabled={disabled}
            onClick={() =>
              run("txt", async () =>
                describeSave(await profileApi.downloadMasterText(language, `${baseName}.txt`), "Texto")
              )
            }
            className={secondaryButton}
          >
            {busy === "txt" ? "Generando…" : "Texto"}
          </button>
        </div>
      </div>
      {notice && (
        <p className="mt-2 text-xs font-semibold text-emerald-700 dark:text-emerald-400">{notice}</p>
      )}
      {error && <p className="mt-2 text-xs text-rose-600 dark:text-rose-400">{error}</p>}
    </div>
  );
}
