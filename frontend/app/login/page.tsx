"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { useAuth } from "@/context/AuthContext";
import { ApiError } from "@/lib/api";

export default function LoginPage() {
  const { login, token, isLoading } = useAuth();
  const router = useRouter();
  const [email, setEmail] = useState("");
  const [password, setPassword] = useState("");
  const [error, setError] = useState<string | null>(null);
  const [submitting, setSubmitting] = useState(false);

  useEffect(() => {
    if (!isLoading && token) {
      router.replace("/");
    }
  }, [isLoading, token, router]);

  async function handleSubmit(e: React.FormEvent) {
    e.preventDefault();
    setError(null);
    setSubmitting(true);
    try {
      await login({ email, password });
      router.replace("/");
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "Could not log in. Please try again.");
    } finally {
      setSubmitting(false);
    }
  }

  return (
    <div className="flex min-h-dvh items-center justify-center px-4 py-10">
      <div className="w-full max-w-sm">
        <div className="mb-8 flex flex-col items-center gap-2 text-center">
          <img src="/icons/icon-192.png" alt="" className="h-12 w-12" />
          <h1 className="text-2xl font-bold text-gray-900 dark:text-gray-100">Welcome back</h1>
          <p className="text-sm text-gray-500 dark:text-gray-400">Log in to JobPilot to keep swiping.</p>
        </div>

        <form onSubmit={handleSubmit} className="space-y-4 rounded-2xl bg-white p-6 shadow-sm ring-1 ring-gray-100 dark:bg-gray-900 dark:ring-gray-800">
          {error && (
            <div className="rounded-lg bg-rose-50 px-3 py-2 text-sm text-rose-700 ring-1 ring-inset ring-rose-200 dark:bg-rose-900/20 dark:text-rose-300 dark:ring-rose-800">
              {error}
            </div>
          )}
          <div>
            <label htmlFor="email" className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
              Email
            </label>
            <input
              id="email"
              type="email"
              required
              autoComplete="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-gray-900 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:focus:ring-brand-900/40"
              placeholder="you@example.com"
            />
          </div>
          <div>
            <label htmlFor="password" className="mb-1 block text-sm font-medium text-gray-700 dark:text-gray-300">
              Password
            </label>
            <input
              id="password"
              type="password"
              required
              autoComplete="current-password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              className="w-full rounded-lg border border-gray-300 px-3 py-2.5 text-gray-900 outline-none focus:border-brand-500 focus:ring-2 focus:ring-brand-100 dark:border-gray-700 dark:bg-gray-800 dark:text-gray-100 dark:focus:ring-brand-900/40"
              placeholder="••••••••"
            />
          </div>
          <button
            type="submit"
            disabled={submitting}
            className="w-full rounded-lg bg-brand-600 px-4 py-2.5 font-semibold text-white transition-colors hover:bg-brand-700 disabled:cursor-not-allowed disabled:opacity-60"
          >
            {submitting ? "Logging in…" : "Log in"}
          </button>
        </form>

        <p className="mt-5 text-center text-sm text-gray-500 dark:text-gray-400">
          New to JobPilot?{" "}
          <Link href="/register" className="font-semibold text-brand-600 hover:text-brand-700 dark:text-brand-400 dark:hover:text-brand-300">
            Create an account
          </Link>
        </p>
      </div>
    </div>
  );
}
