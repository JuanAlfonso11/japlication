"use client";

import Link from "next/link";
import { Suspense, useEffect, useState } from "react";
import { useSearchParams } from "next/navigation";
import { useAuth } from "@/context/AuthContext";

function VerifyEmailContent() {
  const searchParams = useSearchParams();
  const status = searchParams.get("status");
  const { user, token, refreshUser } = useAuth();
  const [refreshed, setRefreshed] = useState(false);

  useEffect(() => {
    if (status === "success" && token && !refreshed) {
      refreshUser().finally(() => setRefreshed(true));
    }
  }, [status, token, refreshed, refreshUser]);

  return (
    <div className="flex min-h-dvh flex-col items-center justify-center gap-4 bg-gray-50 px-4 text-center">
      <div className="flex h-16 w-16 items-center justify-center rounded-2xl bg-brand-600 text-2xl font-bold text-white">
        JF
      </div>

      {status === "success" ? (
        <>
          <h1 className="text-xl font-bold text-gray-900">Cuenta verificada</h1>
          <p className="max-w-sm text-sm text-gray-500">
            Tu correo{user?.email ? ` (${user.email})` : ""} quedó confirmado. Ya puedes usar JobFlow AI
            sin restricciones.
          </p>
        </>
      ) : (
        <>
          <h1 className="text-xl font-bold text-gray-900">No pudimos verificar tu cuenta</h1>
          <p className="max-w-sm text-sm text-gray-500">
            El enlace no es válido o ya expiró (los enlaces de verificación duran 24 horas). Inicia
            sesión y pide que te reenviemos uno nuevo desde el aviso en la parte superior.
          </p>
        </>
      )}

      <Link
        href={token ? "/" : "/login"}
        className="mt-2 rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700"
      >
        {token ? "Ir a Home" : "Iniciar sesión"}
      </Link>
    </div>
  );
}

export default function VerifyEmailPage() {
  return (
    <Suspense fallback={null}>
      <VerifyEmailContent />
    </Suspense>
  );
}
