"use client";

/**
 * La fecha límite de la oferta, con el color que corresponde a lo que queda.
 *
 * Antes JobPilot no tenía el concepto en ninguna parte: una oferta que cierra
 * mañana se veía exactamente igual que una que cierra en un mes, así que la
 * cola de swipe no daba ninguna pista sobre qué mirar primero. Y las ofertas
 * ya cerradas seguían apareciendo.
 *
 * `deadline` null significa que la oferta no la declara — que es lo normal,
 * muchas no lo hacen. En ese caso no se pinta nada: un "sin fecha límite"
 * afirmaría algo que no sabemos.
 */

function diasHasta(iso: string): number | null {
  // Se compara a mediodía UTC para que el cambio de día no dependa del huso
  // del teléfono: la oferta dice un día, no una hora.
  const limite = new Date(`${iso}T12:00:00Z`);
  if (Number.isNaN(limite.getTime())) return null;
  const hoy = new Date();
  const hoyUtc = Date.UTC(hoy.getFullYear(), hoy.getMonth(), hoy.getDate(), 12);
  return Math.round((limite.getTime() - hoyUtc) / 86_400_000);
}

export function DeadlineBadge({
  deadline,
  className = "",
}: {
  deadline?: string | null;
  className?: string;
}) {
  if (!deadline) return null;
  const dias = diasHasta(deadline);
  if (dias === null) return null;

  const fecha = new Date(`${deadline}T12:00:00Z`).toLocaleDateString("es", {
    day: "numeric",
    month: "short",
  });

  let texto: string;
  let tono: string;
  if (dias < 0) {
    texto = `Cerró el ${fecha}`;
    tono = "bg-gray-100 text-gray-500 dark:bg-gray-800 dark:text-gray-400";
  } else if (dias === 0) {
    texto = "Cierra hoy";
    tono = "bg-rose-50 text-rose-700 dark:bg-rose-500/10 dark:text-rose-300";
  } else if (dias === 1) {
    texto = "Cierra mañana";
    tono = "bg-rose-50 text-rose-700 dark:bg-rose-500/10 dark:text-rose-300";
  } else if (dias <= 7) {
    texto = `Cierra en ${dias} días · ${fecha}`;
    tono = "bg-amber-50 text-amber-800 dark:bg-amber-500/10 dark:text-amber-300";
  } else {
    texto = `Hasta el ${fecha}`;
    tono = "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-300";
  }

  return (
    <span
      className={`inline-flex items-center rounded-full px-2 py-0.5 text-[11px] font-semibold ${tono} ${className}`}
      // Los colores no pueden ser la única señal: quien no los distinga
      // necesita el dato igual.
      title={`Fecha límite: ${deadline}`}
    >
      {texto}
    </span>
  );
}

export default DeadlineBadge;
