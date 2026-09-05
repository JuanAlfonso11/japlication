"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { inputClass } from "@/components/ui/Field";
import { ApiError } from "@/lib/api";

export default function RegisterPage() {
  const { register, token, isLoading } = useAuth();
  const router = useRouter();
  const [fullName, setFullName] = useState("");
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
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

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);

    const missing: string[] = [];
    if (password.length < 8) missing.push("al menos 8 caracteres");
    if (!/[A-Z]/.test(password)) missing.push("una mayúscula");
    if (!/\d/.test(password)) missing.push("un número");
    if (!/[^A-Za-z0-9]/.test(password)) missing.push("un carácter especial");
    if (missing.length > 0) {
      setError(`La contraseña debe incluir ${missing.join(", ")}.`);
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
    <div className="flex min-h-dvh items-center justify-center px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center gap-2 text-center">
          <img src="/icons/icon-192.png" alt="" className="h-12 w-12" />
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Crea tu cuenta</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400">
            Arma tu perfil, importa trabajos, y empieza a buscar.
          </p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4 rounded-2xl bg-white p-6 shadow-sm ring-1 ring-gray-100 dark:bg-gray-900 dark:ring-gray-800">
          {error && (
            <div className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700 ring-1 ring-inset ring-rose-200 dark:bg-rose-900/20 dark:text-rose-300 dark:ring-rose-800">
              {error}
            </div>
          )}
          <div>
            <label htmlFor="full_name" className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
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
            <label htmlFor="email" className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
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
              placeholder="you@example.com"
            />
          </div>
          <div>
            <label htmlFor="password" className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
              Contraseña
            </label>
            <input
              id="password"
              type="password"
              required
              minLength={8}
              autoComplete="new-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className={inputClass}
              placeholder="Al menos 8 caracteres"
            />
            <p className="mt-1 text-xs text-gray-400 dark:text-gray-500">
              8+ caracteres, con una mayúscula, un número, y un carácter especial.
            </p>
          </div>
          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-lg bg-brand-600 px-4 py-2.5 font-semibold text-white transition-colors hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {submitting ? "Creando cuenta…" : "Crear cuenta"}
          </button>
        </form>

        <p className="mt-5 text-center text-sm text-gray-500 dark:text-gray-400">
          ¿Ya tienes una cuenta?{" "}
          <Link href="/login" className="font-semibold text-brand-600 hover:text-brand-700 dark:text-brand-400 dark:hover:text-brand-300">
            Iniciar sesión
          </Link>
        </p>
      </div>
    </div>
  );
}
