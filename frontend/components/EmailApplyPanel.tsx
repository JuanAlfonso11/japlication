"use client";

import { useState } from "react";
import ErrorNotice from "@/components/ErrorNotice";
import { ApiError, applicationsApi } from "@/lib/api";
import type { EmailApplyPreview } from "@/lib/types";

/**
 * Postular por correo, para las vacantes que dicen "envía tu CV a...".
 *
 * Es la única vía de envío directo que existe: los ATS que tienen endpoint de
 * envío exigen la clave del empleador, y LinkedIn cierra la cuenta a quien
 * automatiza. Ver backend/app/services/apply_by_email.py.
 *
 * Dos pasos a propósito, y el segundo pide confirmar. Esto manda un correo
 * con tu nombre a una empresa real, y un correo enviado no se retira. Lo que
 * sale es EXACTAMENTE lo que ves en la vista previa: si algo cambió entre
 * medias, el backend lo rechaza y hay que mirar otra vez.
 */
export function EmailApplyPanel({
  jobId,
  applyEmail,
  onSent,
}: {
  jobId: string;
  applyEmail: string;
  onSent: () => void;
}) {
  const [preview, setPreview] = useState<EmailApplyPreview | null>(null);
  const [loading, setLoading] = useState(false);
  const [sending, setSending] = useState(false);
  const [confirming, setConfirming] = useState(false);
  const [sent, setSent] = useState(false);
  const [error, setError] = useState<string | null>(null);

  async function loadPreview() {
    setLoading(true);
    setError(null);
    setConfirming(false);
    try {
      setPreview(await applicationsApi.previewEmail(jobId));
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo preparar el correo.");
    } finally {
      setLoading(false);
    }
  }

  async function send() {
    if (!preview?.fingerprint) return;
    setSending(true);
    setError(null);
    try {
      await applicationsApi.sendEmail(jobId, preview.fingerprint);
      setSent(true);
      onSent();
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo enviar.");
      setConfirming(false);
    } finally {
      setSending(false);
    }
  }

  if (sent) {
    return (
      <div className="rounded-xl bg-emerald-50 p-3 text-xs font-medium text-emerald-800 ring-1 ring-inset ring-emerald-600/20 dark:bg-emerald-900/20 dark:text-emerald-300 dark:ring-emerald-400/30">
        Candidatura enviada a <strong>{preview?.to}</strong>. Quedó registrada en tu pipeline como
        aplicada, y las respuestas llegarán a tu correo.
      </div>
    );
  }

  const bloqueada = (preview?.blockers.length ?? 0) > 0;

  return (
    <div className="rounded-xl bg-emerald-50 p-3 ring-1 ring-inset ring-emerald-600/20 dark:bg-emerald-900/20 dark:ring-emerald-400/30">
      <p className="text-sm font-semibold text-emerald-900 dark:text-emerald-200">
        Esta vacante se postula por correo
      </p>
      <p className="mt-0.5 text-xs text-emerald-800 dark:text-emerald-300">
        La oferta pide enviar el CV a <strong>{applyEmail}</strong>. JobPilot puede mandarlo desde tu
        cuenta, con tu CV adaptado y tu carta adjuntos.
      </p>

      {!preview && (
        <button
          type="button"
          onClick={loadPreview}
          disabled={loading}
          className="mt-2 rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-700 disabled:opacity-60"
        >
          {loading ? "Preparando…" : "Ver el correo antes de enviar"}
        </button>
      )}

      {error && (
        <div className="mt-2">
          <ErrorNotice message={error} />
        </div>
      )}

      {preview && (
        <div className="mt-3 space-y-2">
          {bloqueada && (
            <div className="rounded-lg bg-amber-50 p-2.5 text-xs text-amber-900 ring-1 ring-inset ring-amber-600/20 dark:bg-amber-900/20 dark:text-amber-200">
              <p className="font-semibold">Todavía no se puede enviar:</p>
              {preview.blockers.map((b) => (
                <p key={b} className="mt-1">
                  · {b}
                </p>
              ))}
            </div>
          )}

          {/* El correo tal cual va a salir. Es lo que firma el usuario, así
              que se enseña entero y sin resumir. */}
          <div className="rounded-lg bg-white p-3 text-xs ring-1 ring-gray-200 dark:bg-gray-900 dark:ring-gray-700">
            <p className="text-gray-500 dark:text-gray-400">
              Para: <span className="text-gray-900 dark:text-gray-100">{preview.to}</span>
            </p>
            {preview.reply_to && (
              <p className="text-gray-500 dark:text-gray-400">
                Respuestas a: <span className="text-gray-900 dark:text-gray-100">{preview.reply_to}</span>
              </p>
            )}
            {preview.subject && (
              <p className="mt-1 font-semibold text-gray-900 dark:text-gray-100">{preview.subject}</p>
            )}
            {preview.body && (
              <p className="mt-2 whitespace-pre-wrap text-gray-700 dark:text-gray-300">{preview.body}</p>
            )}
            {preview.attachments.length > 0 && (
              <p className="mt-2 text-gray-500 dark:text-gray-400">
                Adjuntos:{" "}
                {preview.attachments
                  .map((a) => `${a.filename} (${Math.max(1, Math.round(a.size_bytes / 1024))} KB)`)
                  .join(" · ")}
              </p>
            )}
          </div>

          {!bloqueada && !confirming && (
            <button
              type="button"
              onClick={() => setConfirming(true)}
              className="rounded-lg bg-emerald-600 px-4 py-2 text-sm font-semibold text-white hover:bg-emerald-700"
            >
              Enviar candidatura
            </button>
          )}

          {/* Un segundo toque, explícito. Un correo enviado no se retira. */}
          {!bloqueada && confirming && (
            <div className="rounded-lg bg-emerald-100 p-2.5 dark:bg-emerald-900/40">
              <p className="text-xs font-semibold text-emerald-900 dark:text-emerald-100">
                ¿Enviar a {preview.to}? Una vez enviado no se puede retirar.
              </p>
              <div className="mt-2 flex gap-2">
                <button
                  type="button"
                  onClick={send}
                  disabled={sending}
                  className="rounded-lg bg-emerald-700 px-4 py-2 text-sm font-bold text-white hover:bg-emerald-800 disabled:opacity-60"
                >
                  {sending ? "Enviando…" : "Sí, enviar"}
                </button>
                <button
                  type="button"
                  onClick={() => setConfirming(false)}
                  disabled={sending}
                  className="rounded-lg px-3 py-2 text-sm font-semibold text-emerald-800 hover:bg-emerald-200 dark:text-emerald-200 dark:hover:bg-emerald-800"
                >
                  Cancelar
                </button>
              </div>
            </div>
          )}

          <button
            type="button"
            onClick={loadPreview}
            disabled={loading}
            className="block text-[11px] font-semibold text-emerald-700 hover:underline dark:text-emerald-400"
          >
            {loading ? "Actualizando…" : "Volver a generar la vista previa"}
          </button>
        </div>
      )}
    </div>
  );
}

export default EmailApplyPanel;
