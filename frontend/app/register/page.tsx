"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useMemo, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { inputClass } from "@/components/ui/Field";
import Button from "@/components/ui/Button";
import AuthLayout from "@/components/ui/AuthLayout";
import { ApiError } from "@/lib/api";

/** The same four rules the backend enforces in `UserRegister`
 * (`backend/app/schemas/user.py`). Kept as data so the form can show them
 * as a live checklist instead of only failing after a submit — the old
 * flow surfaced them as one red sentence *after* the user had already
 * picked a password, which is the worst possible moment to learn them. */
const PASSWORD_RULES: { label: string; test: (v: string) => boolean }[] = [
  { label: "8+ caracteres", test: (v) => v.length >= 8 },
  { label: "Una mayúscula", test: (v) => /[A-Z]/.test(v) },
  { label: "Un número", test: (v) => /\d/.test(v) },
  { label: "Un carácter especial", test: (v) => /[^A-Za-z0-9]/.test(v) },
];

export default function RegisterPage() {
  const { register, token, isLoading } = useAuth();
  const router = useRouter();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);
  // Suppresses the "already logged in" redirect below right after this
  // page's own register() call — otherwise it would race the explicit
  // redirect to the verification-pending screen and send the user
  // straight to Home instead.
  const [justRegistered, setJustRegistered] = useState(false);

  useEffect(() => {
    if (!isLoading && token && !justRegistered) {
      router.replace("/");
    }
  }, [isLoading, token, justRegistered, router]);

  const ruleState = useMemo(
    () => PASSWORD_RULES.map((rule) => ({ ...rule, ok: rule.test(password) })),
    [password]
  );
  const passwordValid = ruleState.every((r) => r.ok);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    if (!passwordValid) {
      setError("Tu contraseña todavía no cumple los requisitos de abajo.");
      return;
    }

    setSubmitting(true);
    try {
      await register({ email, password, full_name: fullName });
      setJustRegistered(true);
      router.replace("/verify-email?status=pending");
    } catch (err) {
      setError(
        err instanceof ApiError ? err.message : "No se pudo crear tu cuenta. Intenta de nuevo."
      );
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <AuthLayout
      title="Crea tu cuenta"
      subtitle="Arma tu perfil, importa vacantes y deja que JobPilot ordene tu búsqueda."
    >
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
          <label htmlFor="full_name" className="mb-1.5 block text-xs font-semibold text-gray-600 dark:text-gray-400">
            Nombre completo
          </label>
          <input
            id="full_name"
            type="text"
            required
            autoComplete="name"
            value={fullName}
            onChange={(e) => setFullName(e.target.value)}
            className={inputClass}
            placeholder="Ada Lovelace"
          />
        </div>

        <div>
          <label htmlFor="email" className="mb-1.5 block text-xs font-semibold text-gray-600 dark:text-gray-400">
            Correo
          </label>
          <input
            id="email"
            type="email"
            required
            autoComplete="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            className={inputClass}
            placeholder="tu@correo.com"
          />
        </div>

        <div>
          <label htmlFor="password" className="mb-1.5 block text-xs font-semibold text-gray-600 dark:text-gray-400">
            Contraseña
          </label>
          <div className="relative">
            <input
              id="password"
              type={showPassword ? "text" : "password"}
              required
              minLength={8}
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={`${inputClass} pr-12`}
              placeholder="••••••••"
            />
            <button
              type="button"
              onClick={() => setShowPassword((v) => !v)}
              aria-label={showPassword ? "Ocultar contraseña" : "Mostrar contraseña"}
              className="absolute right-1 top-1/2 flex h-9 w-9 -translate-y-1/2 items-center justify-center rounded-lg text-gray-400 transition-colors hover:bg-gray-100 hover:text-gray-600 dark:hover:bg-gray-700 dark:hover:text-gray-300"
            >
              {showPassword ? <EyeOffIcon /> : <EyeIcon />}
            </button>
          </div>

          <ul className="mt-2.5 grid grid-cols-2 gap-x-3 gap-y-1.5">
            {ruleState.map((rule) => (
              <li
                key={rule.label}
                className={`flex items-center gap-1.5 text-[11px] font-medium transition-colors ${
                  rule.ok ? "text-emerald-600 dark:text-emerald-400" : "text-gray-400 dark:text-gray-400"
                }`}
              >
                <span
                  className={`flex h-3.5 w-3.5 shrink-0 items-center justify-center rounded-full transition-colors ${
                    rule.ok
                      ? "bg-emerald-500 text-white"
                      : "bg-gray-200 text-transparent dark:bg-gray-700"
                  }`}
                >
                  <svg width="9" height="9" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round"><path d="M20 6 9 17l-5-5" /></svg>
                </span>
                {rule.label}
              </li>
            ))}
          </ul>
        </div>

        <Button type="submit" size="lg" fullWidth loading={submitting}>
          {submitting ? "Creando cuenta…" : "Crear cuenta"}
        </Button>
      </form>

      <p className="mt-6 text-center text-sm text-gray-500 dark:text-gray-400">
        ¿Ya tienes una cuenta?{" "}
        <Link
          href="/login"
          className="font-bold text-brand-600 transition-colors hover:text-brand-700 dark:text-brand-400 dark:hover:text-brand-300"
        >
          Iniciar sesión
        </Link>
      </p>
    </AuthLayout>
  );
}

function EyeIcon() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7-10-7-10-7Z" />
      <circle cx="12" cy="12" r="3" />
    </svg>
  );
}

function EyeOffIcon() {
  return (
    <svg width="17" height="17" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <path d="M10.6 5.2A9.9 9.9 0 0 1 12 5c6.4 0 10 7 10 7a17.6 17.6 0 0 1-3.4 4.3M6.2 6.2A17.6 17.6 0 0 0 2 12s3.6 7 10 7a9.7 9.7 0 0 0 5.1-1.4" />
      <path d="m2 2 20 20" />
      <path d="M9.9 9.9a3 3 0 0 0 4.2 4.2" />
    </svg>
  );
}
