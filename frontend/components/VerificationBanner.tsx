"use client";

import { useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { ApiError, authApi } from "@/lib/api";

export default function VerificationBanner() {
  const { user } = useAuth();
  const [sending, setSending] = useState(false);
  const [message, setMessage] = useState<string | null>(null);
  const [dismissed, setDismissed] = useState(false);

  if (!user || user.email_verified || dismissed) return null;

  async function handleResend() {
    setSending(true);
    setMessage(null);
    try {
      const res = await authApi.resendVerification();
      setMessage(res.detail);
    } catch (err) {
      setMessage(err instanceof ApiError ? err.message : "No se pudo reenviar el correo.");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="mb-4 flex flex-wrap items-center justify-between gap-2 rounded-2xl bg-accent-50 px-4 py-3 text-sm text-accent-900 ring-1 ring-inset ring-accent-600/20 dark:bg-accent-500/10 dark:text-accent-200 dark:ring-accent-400/25">
      <span className="min-w-0">
        Confirma tu correo (<strong className="font-bold">{user.email}</strong>) para verificar tu
        cuenta.
        {message && <span className="ml-2 text-accent-700 dark:text-accent-300">{message}</span>}
      </span>
      <div className="flex shrink-0 items-center gap-2">
        <button
          type="button"
          onClick={handleResend}
          disabled={sending}
          className="inline-flex min-h-[34px] items-center rounded-lg bg-accent-600 px-3.5 text-xs font-bold text-white transition-colors hover:bg-accent-700 active:scale-95 disabled:opacity-60"
        >
          {sending ? "Enviando…" : "Reenviar correo"}
        </button>
        <button
          type="button"
          onClick={() => setDismissed(true)}
          aria-label="Cerrar"
          className="flex h-8 w-8 items-center justify-center rounded-lg text-accent-600 transition-colors hover:bg-accent-100 dark:text-accent-400 dark:hover:bg-accent-500/15"
        >
          <svg width="14" height="14" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="3" strokeLinecap="round"><path d="M18 6 6 18M6 6l12 12" /></svg>
        </button>
      </div>
    </div>
  );
}
