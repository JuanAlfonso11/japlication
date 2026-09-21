"use client";

import type { WorkAuth } from "@/lib/types";

/**
 * Dónde exige la oferta poder trabajar: "Solo candidatos en EE. UU.",
 * "Exige permiso de trabajo en Canadá · sin patrocinio de visa".
 *
 * El backend lo detecta (services/work_authorization.py) y además dice si
 * deja fuera a TU país (`blocks_you`, según el país de tu perfil):
 *   - true  → rojo: por mucho que encajen las habilidades, no es alcanzable.
 *   - null  → ámbar: la oferta restringe, pero no sabemos si a ti (perfil
 *             sin país, o un "no patrocinamos visa" sin país).
 *   - false → no se pinta: la restricción te incluye, no aporta nada.
 */
export function WorkAuthBadge({
  workAuth,
  className = "",
}: {
  workAuth?: WorkAuth | null;
  className?: string;
}) {
  if (!workAuth || workAuth.blocks_you === false) return null;
  const bloquea = workAuth.blocks_you === true;
  const tono = bloquea
    ? "bg-rose-50 text-rose-700 dark:bg-rose-500/10 dark:text-rose-300"
    : "bg-amber-50 text-amber-800 dark:bg-amber-500/10 dark:text-amber-300";
  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-semibold ${tono} ${className}`}
      title={
        bloquea
          ? "Según el país de tu perfil, esta oferta no te incluye."
          : "La oferta restringe dónde se puede trabajar."
      }
    >
      {bloquea ? "⛔ " : ""}
      {workAuth.label}
    </span>
  );
}

export function ClosedBadge({ closedAt, className = "" }: { closedAt?: string | null; className?: string }) {
  if (!closedAt) return null;
  const fecha = new Date(closedAt).toLocaleDateString("es", { day: "numeric", month: "short" });
  return (
    <span
      className={`inline-flex items-center rounded-full bg-gray-200 px-2 py-0.5 text-[11px] font-semibold text-gray-600 dark:bg-gray-700 dark:text-gray-300 ${className}`}
      title={`Comprobado el ${fecha}: la oferta ya no existe en su origen.`}
    >
      Oferta cerrada
    </span>
  );
}

export default WorkAuthBadge;
