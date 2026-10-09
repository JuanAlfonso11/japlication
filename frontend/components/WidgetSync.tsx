"use client";

import { useEffect, useRef } from "react";
import { App } from "@capacitor/app";
import type { PluginListenerHandle } from "@capacitor/core";
import { useAuth } from "@/context/AuthContext";
import { isNativeApp } from "@/lib/platform";
import { clearWidgets, refreshWidgets } from "@/lib/widgets";

/** Mantiene al día los widgets de la pantalla de inicio (ver lib/widgets.ts).
 *
 * Refresca al abrir la app y al volver a ella, y sobre todo al SALIR: es
 * justo cuando la persona vuelve a su pantalla de inicio y mira el widget.
 * Lo que cambió dentro de la app (un swipe, un estado en Pipeline) ya está
 * en el servidor para entonces.
 *
 * Al cerrar sesión borra los datos, para que el widget no siga enseñando la
 * cola de alguien que ya salió. No renderiza nada. */
export default function WidgetSync() {
  const { token } = useAuth();
  const hadSession = useRef(false);

  useEffect(() => {
    if (!isNativeApp()) return;

    if (!token) {
      if (hadSession.current) void clearWidgets();
      hadSession.current = false;
      return;
    }
    hadSession.current = true;

    void refreshWidgets(0);

    let handle: PluginListenerHandle | undefined;
    let cancelled = false;
    App.addListener("appStateChange", ({ isActive }) => {
      // Saliendo: sin espera mínima, es el refresco que de verdad se ve.
      void refreshWidgets(isActive ? 30_000 : 0);
    })
      .then((h) => {
        if (cancelled) h.remove();
        else handle = h;
      })
      .catch(() => {
        // Sin el plugin App no hay eventos; el refresco al abrir basta.
      });

    return () => {
      cancelled = true;
      handle?.remove();
    };
  }, [token]);

  return null;
}
