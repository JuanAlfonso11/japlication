"use client";

import { useEffect, useState } from "react";
import { ApiError, applyAgentApi } from "@/lib/api";
import { MODE_LABELS } from "@/lib/applyDraft";
import type { ApplyMode, ApplySettings } from "@/lib/types";

const MODES: ApplyMode[] = ["save", "review", "auto"];

/** Qué hace el swipe a la derecha. Vive en Perfil → Ajustes y en la bandeja
 * de aplicaciones, porque es una decisión que uno revisa después de ver
 * cómo salen las primeras. */
export default function ApplyModeSettings({
  onChange,
  compact = false,
}: {
  onChange?: (settings: ApplySettings) => void;
  compact?: boolean;
}) {
  const [settings, setSettings] = useState<ApplySettings | null>(null);
  const [saving, setSaving] = useState<ApplyMode | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let cancelled = false;
    applyAgentApi
      .settings()
      .then((s) => {
        if (!cancelled) setSettings(s);
      })
      .catch((err) => {
        if (!cancelled) setError(err instanceof ApiError ? err.message : "No se pudo leer el ajuste.");
      });
    return () => {
      cancelled = true;
    };
  }, []);

  async function choose(mode: ApplyMode) {
    if (!settings || mode === settings.apply_mode || saving) return;
    setSaving(mode);
    setError(null);
    try {
      const next = await applyAgentApi.setMode(mode);
      setSettings(next);
      onChange?.(next);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo guardar el ajuste.");
    } finally {
      setSaving(null);
    }
  }

  return (
    <div className="space-y-2.5">
      {!compact && (
        <div>
          <p className="text-sm font-medium text-gray-700 dark:text-gray-300">Al deslizar a la derecha</p>
          <p className="text-xs text-gray-500 dark:text-gray-400">
            JobPilot nunca inventa datos, no responde por ti consentimientos ni preguntas sensibles, y no toca
            un CAPTCHA: eso siempre te lo deja a ti.
          </p>
        </div>
      )}
      <div role="radiogroup" aria-label="Qué hace el swipe a la derecha" className="space-y-1.5">
        {MODES.map((mode) => {
          const selected = settings?.apply_mode === mode;
          return (
            <button
              key={mode}
              type="button"
              role="radio"
              aria-checked={selected}
              disabled={!settings || !!saving}
              onClick={() => choose(mode)}
              className={`w-full rounded-xl px-3.5 py-2.5 text-left ring-1 ring-inset transition-colors disabled:opacity-60 ${
                selected
                  ? "bg-brand-600 text-white ring-brand-600 dark:bg-brand-200 dark:text-gray-950 dark:ring-brand-200"
                  : "bg-gray-50 text-gray-700 ring-gray-200 hover:bg-gray-100 dark:bg-gray-800/60 dark:text-gray-200 dark:ring-gray-700 dark:hover:bg-gray-800"
              }`}
            >
              <span className="flex items-center justify-between gap-2 text-sm font-semibold">
                {MODE_LABELS[mode].title}
                {saving === mode ? <span aria-hidden="true">…</span> : selected && <span aria-hidden="true">✓</span>}
              </span>
              <span
                className={`mt-0.5 block text-xs leading-relaxed ${
                  selected ? "text-white/80 dark:text-gray-800" : "text-gray-500 dark:text-gray-400"
                }`}
              >
                {MODE_LABELS[mode].body}
              </span>
            </button>
          );
        })}
      </div>
      {settings && settings.apply_mode === "auto" && (
        <p className="text-xs text-gray-500 dark:text-gray-400">
          Hoy salieron solas {settings.auto_sent_today} de {settings.daily_auto_limit}. Cada una espera{" "}
          {settings.undo_minutes} min antes de salir.
        </p>
      )}
      {settings && settings.apply_mode !== "save" && !settings.agent_available && (
        <p className="rounded-lg bg-amber-50 p-2.5 text-xs text-amber-900 ring-1 ring-inset ring-amber-600/20 dark:bg-amber-900/20 dark:text-amber-200">
          El envío desde el servidor no está activo: las de Greenhouse quedan listas y las envías tú en la página
          (la extensión las llena). Las que piden correo sí salen desde aquí.
        </p>
      )}
      {error && <p className="text-xs text-rose-600 dark:text-rose-400">{error}</p>}
    </div>
  );
}
