"use client";

import { useState } from "react";
import RouteGuard from "@/components/RouteGuard";
import ErrorNotice from "@/components/ErrorNotice";
import ImportedJobCard from "@/components/ImportedJobCard";
import { inputClass, textareaClass } from "@/components/ui/Field";
import { ApiError, jobsApi } from "@/lib/api";
import { importAndMatch } from "@/lib/jobActions";
import type { Job } from "@/lib/types";

function ImportByUrl({ onImported }: { onImported: (job: Job) => void }) {
  const [url, setUrl] = useState("");
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setLoading(true);
    try {
      const job = await jobsApi.import({ url });
      onImported(await importAndMatch(job));
      setUrl("");
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "No se pudo importar esa vacante."
      );
    } finally {
      setLoading(false);
    }
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

function ManualJobForm({ onImported }: { onImported: (job: Job) => void }) {
  const [title, setTitle] = useState("");
  const [company, setCompany] = useState("");
  const [location, setLocation] = useState("");
  const [description, setDescription] = useState("");
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
      <div className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        <label className="block">
          <span className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">Título</span>
          <input required className={inputClass} value={title} onChange={(e) => setTitle(e.target.value)} />
        </label>
        <label className="block">
          <span className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">Empresa</span>
          <input required className={inputClass} value={company} onChange={(e) => setCompany(e.target.value)} />
        </label>
        <label className="block sm:col-span-2">
          <span className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">Ubicación</span>
          <input className={inputClass} value={location} onChange={(e) => setLocation(e.target.value)} />
        </label>
      </div>
      <label className="block">
        <span className="mb-1 block text-xs font-medium text-gray-600 dark:text-gray-400">Descripción completa</span>
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
  const [mode, setMode] = useState<"url" | "manual">("url");
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
          <a href="/discover" className="font-semibold text-brand-600 hover:underline dark:text-brand-400">
            Buscar
          </a>
          .
        </p>
      </div>

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
          <ImportByUrl onImported={setLastImported} />
        ) : (
          <ManualJobForm onImported={setLastImported} />
        )}
      </div>

      {lastImported && <ImportedJobCard job={lastImported} />}
    </div>
  );
}

export default function ImportJobPage() {
  return (
    <RouteGuard>
      <ImportContent />
    </RouteGuard>
  );
}
