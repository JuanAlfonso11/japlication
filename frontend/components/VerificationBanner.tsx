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
      setMessage(err instanceof ApiError ? err.message : "Could not resend the email.");
    } finally {
      setSending(false);
    }
  }

  return (
    <div className="mb-4 flex flex-wrap items-center justify-between gap-2 rounded-xl bg-amber-50 px-4 py-3 text-sm text-amber-800 ring-1 ring-inset ring-amber-600/20 dark:bg-amber-900/20 dark:text-amber-300 dark:ring-amber-400/30">
      <span>
        Confirma tu correo (<strong>{user.email}</strong>) para verificar tu cuenta.
        {message && <span className="ml-2 text-amber-700 dark:text-amber-400">{message}</span>}
      </span>
      <div className="flex items-center gap-3">
        <button
          type="button"
          onClick={handleResend}
          disabled={sending}
          className="rounded-lg bg-amber-600 px-3 py-1.5 text-xs font-semibold text-white hover:bg-amber-700 disabled:opacity-60"
        >
          {sending ? "Enviando…" : "Reenviar correo"}
        </button>
        <button
          type="button"
          onClick={() => setDismissed(true)}
          aria-label="Cerrar"
          className="text-amber-500 hover:text-amber-700 dark:text-amber-400 dark:hover:text-amber-300"
        >
          ✕
        </button>
      </div>
    </div>
  );
}
