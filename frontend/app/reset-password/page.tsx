"use client";

import Link from "next/link";
import { Suspense, useState } from "react";
import { useSearchParams } from "next/navigation";
import { inputClass } from "@/components/ui/Field";
import Button, { buttonClass } from "@/components/ui/Button";
import AuthLayout from "@/components/ui/AuthLayout";
import { ApiError, authApi } from "@/lib/api";
import { PASSWORD_RULES } from "@/lib/passwordRules";

const linkClass =
  "font-bold text-brand-600 transition-colors hover:text-brand-700 dark:text-brand-400 dark:hover:text-brand-300";

function ResetPasswordContent() {
  const token = useSearchParams().get("token") ?? "";
  const [password, setPassword] = useState("");
  const [confirm, setConfirm] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [done, setDone] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  const rules = PASSWORD_RULES.map((rule) => ({ ...rule, ok: rule.test(password) }));

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    if (!rules.every((r) => r.ok)) {
      setError("Tu contraseña todavía no cumple los requisitos de abajo.");
      return;
    }
    if (password !== confirm) {
      setError("Las contraseñas no coinciden.");
      return;
    }
    setSubmitting(true);
    try {
      const res = await authApi.resetPassword(token, password);
      setDone(res.detail);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "No se pudo cambiar la contraseña. Intenta de nuevo.");
    } finally {
      setSubmitting(false);
    }
  }

  if (!token) {
    return (
      <AuthLayout title="Enlace incompleto" subtitle="Abre el enlace completo del correo, o pide uno nuevo.">
        <p className="text-center text-sm">
          <Link href="/forgot-password" className={linkClass}>
            Pedir un enlace nuevo
          </Link>
        </p>
      </AuthLayout>
    );
  }

  if (done) {
    return (
      <AuthLayout title="Contraseña actualizada" subtitle={done}>
        <Link href="/login" className={buttonClass({ size: "lg", fullWidth: true })}>
          Iniciar sesión
        </Link>
      </AuthLayout>
    );
  }

  return (
    <AuthLayout title="Crea una nueva contraseña" subtitle="Por seguridad, se cerrará la sesión en todos tus dispositivos.">
      <form onSubmit={handleSubmit} className="space-y-4">
        {error && (
          <div
            role="alert"
            className="rounded-xl bg-rose-50 px-3.5 py-2.5 text-sm text-rose-700 ring-1 ring-inset ring-rose-200 dark:bg-rose-500/10 dark:text-rose-300 dark:ring-rose-500/30"
          >
            {error}
          </div>
        )}
        <div>
          <label htmlFor="password" className="mb-1.5 block text-xs font-semibold text-gray-600 dark:text-gray-400">
            Nueva contraseña
          </label>
          <input
            id="password"
            type="password"
            required
            autoComplete="new-password"
            value={password}
            onChange={(e) => setPassword(e.target.value)}
            className={inputClass}
          />
          <ul className="mt-2 grid grid-cols-2 gap-1 text-xs">
            {rules.map((r) => (
              <li key={r.label} className={r.ok ? "text-emerald-600 dark:text-emerald-400" : "text-gray-400"}>
                {r.ok ? "✓" : "•"} {r.label}
              </li>
            ))}
          </ul>
        </div>
        <div>
          <label htmlFor="confirm" className="mb-1.5 block text-xs font-semibold text-gray-600 dark:text-gray-400">
            Repite la contraseña
          </label>
          <input
            id="confirm"
            type="password"
            required
            autoComplete="new-password"
            value={confirm}
            onChange={(e) => setConfirm(e.target.value)}
            className={inputClass}
          />
        </div>
        <Button type="submit" size="lg" fullWidth loading={submitting}>
          {submitting ? "Guardando…" : "Guardar contraseña"}
        </Button>
      </form>
    </AuthLayout>
  );
}

export default function ResetPasswordPage() {
  // useSearchParams needs a Suspense boundary in the app router.
  return (
    <Suspense>
      <ResetPasswordContent />
    </Suspense>
  );
}
