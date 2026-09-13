"use client";

import { useEffect, useState } from "react";
import SectionCard from "@/components/profile/SectionCard";
import { ApiError, systemApi } from "@/lib/api";
import type { HeartbeatInfo } from "@/lib/types";

// Expected job name -> {label, max age before it's flagged stale}. Kept
// here (not derived from the backend) since these intervals live in the
// *.ps1 schedules (install-*-schedule.ps1), not in anything the API
// exposes — a little slack is added over each script's own interval so a
// few minutes' scheduling jitter doesn't read as "broken".
const EXPECTED_JOBS: { name: string; label: string; maxAgeHours: number }[] = [
  { name: "watchdog", label: "Vigilancia de contenedores (cada 15 min)", maxAgeHours: 0.5 },
  { name: "job_sweep", label: "Búsqueda de vacantes nuevas (cada 2 horas)", maxAgeHours: 2.5 },
  { name: "stale_check", label: "Aviso de aplicaciones sin novedades (diario)", maxAgeHours: 26 },
  { name: "backup", label: "Respaldo de la base de datos (diario)", maxAgeHours: 26 },
];

function relativeTime(iso: string): string {
  const diffMs = Date.now() - new Date(iso).getTime();
  const minutes = Math.round(diffMs / 60000);
  if (minutes < 1) return "hace un momento";
  if (minutes < 60) return `hace ${minutes} min`;
  const hours = Math.round(minutes / 60);
  if (hours < 24) return `hace ${hours} h`;
  const days = Math.round(hours / 24);
  return `hace ${days} día${days === 1 ? "" : "s"}`;
}

export default function SystemStatusPanel() {
  const [heartbeats, setHeartbeats] = useState<HeartbeatInfo[] | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    systemApi
      .status()
      .then(setHeartbeats)
      .catch((err) => setError(err instanceof ApiError ? err.message : "No se pudo cargar el estado."));
  }, []);

  return (
    <SectionCard
      title="Estado del sistema"
      description="Los procesos que corren en segundo plano en tu PC — no necesitas abrir Task Scheduler para saber si siguen vivos."
    >
      {error && <p className="text-xs text-rose-600 dark:text-rose-400">{error}</p>}
      {heartbeats === null && !error && <p className="text-xs text-gray-400 dark:text-gray-400">Cargando…</p>}
      {heartbeats && (
        <div className="space-y-2">
          {EXPECTED_JOBS.map((expected) => {
            const hb = heartbeats.find((h) => h.job_name === expected.name);
            const ageHours = hb ? (Date.now() - new Date(hb.last_run_at).getTime()) / 3600000 : null;
            const healthy = hb != null && hb.last_status === "ok" && ageHours != null && ageHours <= expected.maxAgeHours;
            const dotColor = !hb
              ? "bg-gray-300 dark:bg-gray-600"
              : healthy
                ? "bg-emerald-500"
                : "bg-rose-500";
            return (
              <div key={expected.name} className="flex items-center justify-between gap-3 text-sm">
                <div className="flex items-center gap-2">
                  <span className={`h-2 w-2 shrink-0 rounded-full ${dotColor}`} />
                  <span className="text-gray-700 dark:text-gray-300">{expected.label}</span>
                </div>
                <span className="shrink-0 text-xs text-gray-400 dark:text-gray-400">
                  {hb ? relativeTime(hb.last_run_at) : "sin datos aún"}
                </span>
              </div>
            );
          })}
        </div>
      )}
    </SectionCard>
  );
}
