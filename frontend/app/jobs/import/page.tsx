"use client";

import { Suspense, useCallback, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useSearchParams } from "next/navigation";
import RouteGuard from "@/components/RouteGuard";
import Spinner from "@/components/Spinner";
import ErrorNotice from "@/components/ErrorNotice";
import ImportedJobCard from "@/components/ImportedJobCard";
import { inputClass, textareaClass } from "@/components/ui/Field";
import { ApiError, jobsApi } from "@/lib/api";
import { importAndMatch } from "@/lib/jobActions";
import { extractSharedUrl } from "@/lib/sharedText";
import type { Job } from "@/lib/types";

function ImportByUrl({
  onImported,
  initialUrl = "",
  autoStart = false,
}: {
  onImported: (job: Job) => void;
  /** Pre-filled when the page was opened from Android's share sheet. */
  initialUrl?: string;
  /** Fires the import immediately, so sharing a job is one tap end to end
   * instead of "share, then tap Importar". */
  autoStart?: boolean;
}) {
  const [url, setUrl] = useState(initialUrl);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  const runImport = useCallback(
    async (target: string) => {
      setError(null);
      setLoading(true);
      try {
        const job = await jobsApi.import({ url: target });
        onImported(await importAndMatch(job));
        setUrl("");
      } catch (err) {
        setError(err instanceof ApiError ? err.message : "No se pudo importar esa vacante.");
      } finally {
        setLoading(false);
      }
    },
    [onImported]
  );

  // Guards against a second run: React 18 mounts effects twice in dev, and
  // importing the same posting twice would create a duplicate job row.
  const autoStarted = useRef(false);
  useEffect(() => {
    if (!autoStart || !initialUrl || autoStarted.current) return;
    autoStarted.current = true;
    runImport(initialUrl);
  }, [autoStart, initialUrl, runImport]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    runImport(url);
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      {error && <ErrorNotice message={error} />}
      <label className="block">
        <span className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">URL de la vacante</span>
        <input
          type="url"
          required
          value={url}
          onChange={(e) => setUrl(e.target.value)}
          placeholder="https://empresa.com/careers/senior-engineer"
          className={inputClass}
        />
      </label>
      <button
        type="submit"
        disabled={loading}
        className="w-full rounded-lg bg-brand-600 px-4 py-2.5 font-semibold text-white hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto"
      >
        {loading ? "Importando…" : "Importar trabajo"}
      </button>
    </form>
  );
}

/** Banner shown when the page was opened from the share sheet. Sharing
 * launches the app, which is disorienting without a line saying why you're
 * suddenly looking at this screen. */
function SharedNotice({ url, rawText }: { url: string | null; rawText: string }) {
  if (url) {
    return (
      <div className="rounded-2xl bg-brand-50 p-3.5 ring-1 ring-inset ring-brand-100 dark:bg-brand-500/10 dark:ring-brand-500/20">
        <p className="text-xs font-bold text-brand-900 dark:text-brand-200">
          Importando lo que compartiste
        </p>
        <p className="mt-1 truncate text-xs text-brand-700 dark:text-brand-300">{url}</p>
      </div>
    );
  }

  return (
    <div className="rounded-2xl bg-accent-50 p-3.5 ring-1 ring-inset ring-accent-600/20 dark:bg-accent-500/10 dark:ring-accent-400/25">
      <p className="text-xs font-bold text-accent-900 dark:text-accent-200">
        No encontramos un enlace en lo que compartiste
      </p>
      <p className="mt-1 text-xs leading-relaxed text-accent-800 dark:text-accent-300">
        Lo dejamos abajo para que lo cargues a mano, o pega la URL de la vacante arriba.
      </p>
      {rawText && (
        <p className="mt-2 line-clamp-3 rounded-lg bg-white/60 p-2 text-[11px] text-gray-600 dark:bg-black/20 dark:text-gray-400">
          {rawText}
        </p>
      )}
    </div>
  );
}

function ManualJobForm({
  onImported,
  initialDescription = "",
}: {
  onImported: (job: Job) => void;
  /** Carries over text shared from another app when it held no link, so the
   * user doesn't have to go back and copy it again. */
  initialDescription?: string;
}) {
  const [title, setTitle] = useState("");
  const [company, setCompany] = useState("");
  const [location, setLocation] = useState("");
  const [description, setDescription] = useState(initialDescription);
  const [requirements, setRequirements] = useState("");
  const [skills, setSkills] = useState("");
  const [requiresCoverLetter, setRequiresCoverLetter] = useState(false);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const job = await jobsApi.create({
        title,
        company,
        location,
        description,
        requirements: requirements
          .split("\n")
          .map((r) => r.trim())
          .filter(Boolean),
        skills_required: skills
          .split(",")
          .map((s) => s.trim())
          .filter(Boolean)
          .map((name) => ({ name, importance: "required" as const })),
        requires_cover_letter: requiresCoverLetter,
      });
      onImported(await importAndMatch(job));
      setTitle("");
      setCompany("");
      setLocation("");
      setDescription("");
      setRequirements("");
      setSkills("");
      setRequiresCoverLetter(false);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo guardar ese trabajo.");
    } finally {
      setLoading(false);
    }
  }

  return (
    <form onSubmit={handleSubmit} className="space-y-3">
      {error && <ErrorNotice message={error} />}
      {/* Título, Empresa and Descripción are the three the form refuses
          without, and they looked exactly like the optional ones until a
          submit failed. */}
      <p className="text-[11px] text-gray-400 dark:text-gray-400">
        Los campos con <span className="font-bold text-brand-600 dark:text-brand-400">*</span> son
        obligatorios.
      </p>
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label className="block">
          <span className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">
            Título <span className="font-bold text-brand-600 dark:text-brand-400">*</span>
          </span>
          <input required className={inputClass} value={title} onChange={(e) => setTitle(e.target.value)} />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">
            Empresa <span className="font-bold text-brand-600 dark:text-brand-400">*</span>
          </span>
          <input required className={inputClass} value={company} onChange={(e) => setCompany(e.target.value)} />
        </label>
        <label className="block sm:col-span-2">
          <span className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">Ubicación</span>
          <input className={inputClass} value={location} onChange={(e) => setLocation(e.target.value)} />
        </label>
      </div>
      <label className="block">
        <span className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">
          Descripción completa <span className="font-bold text-brand-600 dark:text-brand-400">*</span>
        </span>
        <textarea
          required
          className={`${textareaClass} min-h-[120px]`}
          value={description}
          onChange={(e) => setDescription(e.target.value)}
          placeholder="Pega aquí el texto completo de la descripción…"
        />
      </label>
      <label className="block">
        <span className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">
          Requisitos (uno por línea)
        </span>
        <textarea
          className={`${textareaClass} min-h-[90px]`}
          value={requirements}
          onChange={(e) => setRequirements(e.target.value)}
          placeholder={"5+ años de experiencia en backend\nExperiencia con sistemas distribuidos"}
        />
      </label>
      <label className="block">
        <span className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">
          Habilidades (separadas por coma)
        </span>
        <input
          className={inputClass}
          value={skills}
          onChange={(e) => setSkills(e.target.value)}
          placeholder="C#, SQL, Kubernetes"
        />
      </label>
      <label className="flex items-center gap-2 text-sm text-gray-700 dark:text-gray-300">
        <input
          type="checkbox"
          checked={requiresCoverLetter}
          onChange={(e) => setRequiresCoverLetter(e.target.checked)}
          className="h-4 w-4 rounded border-gray-300 text-brand-600 focus:ring-brand-500 dark:border-gray-600"
        />
        Requiere carta de presentación
      </label>
      <button
        type="submit"
        disabled={loading}
        className="w-full rounded-lg bg-brand-600 px-4 py-2.5 font-semibold text-white hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60 sm:w-auto"
      >
        {loading ? "Guardando…" : "Agregar trabajo"}
      </button>
    </form>
  );
}

function ImportContent() {
  const searchParams = useSearchParams();
  // Two different callers land here, and they don't agree on parameters:
  //   - the native app, where MainActivity forwards the whole shared blob
  //     as ?shared=
  //   - the installed PWA, where the browser splits a share into the
  //     title/text/url fields declared in manifest.json's share_target
  // A normal visit has none of them and the screen behaves as it always did.
  const sharedText = searchParams.get("shared");
  const sharedUrlParam = searchParams.get("shared_url");
  const sharedTitle = searchParams.get("shared_title");

  // The browser's own `url` field is authoritative when present; otherwise
  // dig the link out of the free text, which is where every app that wraps
  // the link in prose puts it.
  const sharedUrl = sharedUrlParam ?? extractSharedUrl(sharedText) ?? extractSharedUrl(sharedTitle);
  // What to show/keep when no link was found at all.
  const sharedRaw = sharedText ?? sharedTitle;
  const wasShared = Boolean(sharedText || sharedUrlParam || sharedTitle);

  const [mode, setMode] = useState<"url" | "manual">(
    wasShared && !sharedUrl ? "manual" : "url"
  );
  const [lastImported, setLastImported] = useState<Job | null>(null);

  return (
    <div className="space-y-6 pb-4 animate-fade-in">
      <div>
        <h1 className="font-display text-[26px] font-extrabold leading-tight tracking-display-tight text-gray-900 dark:text-gray-50">
          Agregar una vacante
        </h1>
        <p className="mt-1 max-w-[52ch] text-sm leading-relaxed text-gray-500 dark:text-gray-400">
          Pega la URL o el texto de una vacante y JobPilot la convierte en un trabajo estructurado,
          comparado contra tu perfil. ¿Buscas vacantes nuevas? Prueba{" "}
          {/* A plain <a> reloaded the whole WebView — on the phone that is
              the app restarting, splash and all, to reach a tab that is one
              row away in the bottom bar. */}
          <Link href="/discover" className="font-semibold text-brand-600 hover:underline dark:text-brand-400">
            Buscar
          </Link>
          .
        </p>
      </div>

      {wasShared && <SharedNotice url={sharedUrl} rawText={sharedRaw ?? ""} />}

      <div className="rounded-2xl bg-white p-5 shadow-sm ring-1 ring-gray-100 dark:bg-gray-900 dark:ring-gray-800">
        <div className="mb-4 inline-flex rounded-lg bg-gray-100 p-1 text-sm font-medium dark:bg-gray-800">
          <button
            type="button"
            onClick={() => setMode("url")}
            className={`rounded-md px-3 py-1.5 transition-colors ${
              mode === "url"
                ? "bg-white shadow-sm text-gray-900 dark:bg-gray-700 dark:text-gray-100"
                : "text-gray-500 dark:text-gray-400"
            }`}
          >
            Desde URL
          </button>
          <button
            type="button"
            onClick={() => setMode("manual")}
            className={`rounded-md px-3 py-1.5 transition-colors ${
              mode === "manual"
                ? "bg-white shadow-sm text-gray-900 dark:bg-gray-700 dark:text-gray-100"
                : "text-gray-500 dark:text-gray-400"
            }`}
          >
            Pegar manualmente
          </button>
        </div>

        {mode === "url" ? (
          <ImportByUrl
            onImported={setLastImported}
            initialUrl={sharedUrl ?? ""}
            autoStart={Boolean(sharedUrl)}
          />
        ) : (
          <ManualJobForm onImported={setLastImported} initialDescription={sharedRaw ?? ""} />
        )}
      </div>

      {lastImported && <ImportedJobCard job={lastImported} />}
    </div>
  );
}

export default function ImportJobPage() {
  return (
    <RouteGuard>
      {/* useSearchParams needs a Suspense boundary to keep this route
          statically renderable. */}
      <Suspense fallback={<Spinner />}>
        <ImportContent />
      </Suspense>
    </RouteGuard>
  );
}
