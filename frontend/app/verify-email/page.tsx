"use client";

import Link from "next/link";
import { Suspense, useEffect, useState } from "react";
import { useRouter, useSearchParams } from "next/navigation";
import { useAuth } from "@/context/AuthContext";
import { ApiError, authApi } from "@/lib/api";

const AUTO_REDIRECT_SECONDS = 3;

function VerifyEmailContent() {
  const searchParams = useSearchParams();
  const router = useRouter();
  const status = searchParams.get("status");
  const { user, token, refreshUser } = useAuth();
  const [refreshed, setRefreshed] = useState(false);
  const [resending, setResending] = useState(false);
  const [resendMessage, setResendMessage] = useState<string | null>(null);
  const [redirectIn, setRedirectIn] = useState(AUTO_REDIRECT_SECONDS);

  useEffect(() => {
    if (status === "success" && token && !refreshed) {
      refreshUser().finally(() => setRefreshed(true));
    }
  }, [status, token, refreshed, refreshUser]);

  // Verifying via the email link opens a normal page — this session only
  // has an active token if it happens to share storage with the app (e.g.
  // the link was tapped inside the app's own webview). When it does, take
  // the user straight back into the app instead of leaving them stranded
  // on a standalone confirmation screen. True automatic app-switching from
  // an external browser would need Android App Links, which can't be
  // verified reliably against a Tailscale-only (non-public) domain.
  useEffect(() => {
    if (status !== "success" || !token || !refreshed) return;
    if (redirectIn <= 0) {
      router.replace("/");
      return;
    }
    const t = setTimeout(() => setRedirectIn((s) => s - 1), 1000);
    return () => clearTimeout(t);
  }, [status, token, refreshed, redirectIn, router]);

  async function handleResend() {
    setResending(true);
    setResendMessage(null);
    try {
      const res = await authApi.resendVerification();
      setResendMessage(res.detail);
    } catch (err) {
      setResendMessage(err instanceof ApiError ? err.message : "Could not resend the email.");
    } finally {
      setResending(false);
    }
  }

  return (
    <div className="flex min-h-dvh flex-col items-center justify-center gap-4 bg-gray-50 px-4 text-center dark:bg-gray-950">
      <img src="/icons/icon-192.png" alt="" className="h-16 w-16" />

      {status === "success" ? (
        <>
          <h1 className="text-xl font-bold text-gray-900 dark:text-gray-100">Cuenta verificada</h1>
          <p className="max-w-sm text-sm text-gray-500 dark:text-gray-400">
            Tu correo{user?.email ? ` (${user.email})` : ""} quedó confirmado. Ya puedes usar JobPilot
            sin restricciones.
          </p>
          {token && (
            <p className="text-xs text-gray-400 dark:text-gray-500">
              Te llevamos a Home en {redirectIn}s…
            </p>
          )}
        </>
      ) : status === "pending" ? (
        <>
          <span className="text-4xl">📬</span>
          <h1 className="text-xl font-bold text-gray-900 dark:text-gray-100">Revisa tu correo</h1>
          <p className="max-w-sm text-sm text-gray-500 dark:text-gray-400">
            Te mandamos un enlace de verificación{user?.email ? ` a ${user.email}` : ""}. Ábrelo desde tu
            correo para confirmar tu cuenta — el enlace dura 10 minutos, si se vence puedes pedir uno
            nuevo aquí abajo.
          </p>
        </>
      ) : (
        <>
          <h1 className="text-xl font-bold text-gray-900 dark:text-gray-100">No pudimos verificar tu cuenta</h1>
          <p className="max-w-sm text-sm text-gray-500 dark:text-gray-400">
            El enlace no es válido o ya expiró (los enlaces de verificación duran solo 10 minutos, para
            mayor control). {token ? "Pide uno nuevo aquí abajo." : "Inicia sesión y pide uno nuevo."}
          </p>
        </>
      )}

      {status !== "success" && token && (
        <div className="flex flex-col items-center gap-2">
          <button
            type="button"
            onClick={handleResend}
            disabled={resending}
            className="rounded-lg bg-brand-600 px-4 py-2 text-sm font-semibold text-white hover:bg-brand-700 disabled:opacity-60"
          >
            {resending ? "Enviando…" : "Reenviar correo de verificación"}
          </button>
          {resendMessage && <p className="text-xs text-gray-500 dark:text-gray-400">{resendMessage}</p>}
        </div>
      )}

      <Link
        href={token ? "/" : "/login"}
        className="mt-1 text-sm font-semibold text-brand-600 hover:text-brand-700 dark:text-brand-400 dark:hover:text-brand-300"
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
