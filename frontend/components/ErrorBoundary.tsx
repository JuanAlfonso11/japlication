"use client";

import { Component, type ErrorInfo, type ReactNode } from "react";
import { reportClientError } from "@/lib/errorReporting";

/** Catches a render crash instead of letting React blank the screen.
 *
 * A component throwing during render unmounts the whole tree — on the phone
 * that shows up as the app suddenly going white, with nothing to report
 * beyond "se puso en blanco". This turns that into a readable message plus
 * a row in `error_logs` with the component stack, which is what actually
 * says *which* component broke.
 *
 * Class component because error boundaries have no hooks equivalent —
 * `componentDidCatch` and `getDerivedStateFromError` exist only here.
 */
export default class ErrorBoundary extends Component<
  { children: ReactNode },
  { error: Error | null }
> {
  state: { error: Error | null } = { error: null };

  static getDerivedStateFromError(error: Error) {
    return { error };
  }

  componentDidCatch(error: Error, info: ErrorInfo) {
    // The component stack is the valuable half — the plain stack usually
    // points at React internals, not at the component that actually threw.
    const withComponentStack = new Error(error.message);
    withComponentStack.name = error.name;
    withComponentStack.stack = `${error.stack ?? ""}\n\nComponent stack:${info.componentStack ?? ""}`;
    reportClientError(withComponentStack, { kind: "ReactRenderError" });
  }

  render() {
    if (!this.state.error) return this.props.children;

    return (
      <div className="flex min-h-[60dvh] flex-col items-center justify-center gap-3 px-6 text-center">
        <span className="flex h-14 w-14 items-center justify-center rounded-2xl bg-rose-50 text-rose-600 dark:bg-rose-500/15 dark:text-rose-400">
          <svg width="26" height="26" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" strokeLinecap="round" strokeLinejoin="round">
            <path d="M12 9v4" />
            <path d="M12 17h.01" />
            <path d="M10.3 3.9 1.8 18a2 2 0 0 0 1.7 3h17a2 2 0 0 0 1.7-3L13.7 3.9a2 2 0 0 0-3.4 0Z" />
          </svg>
        </span>
        <p className="font-display text-lg font-extrabold tracking-display-tight text-gray-900 dark:text-gray-100">
          Esta pantalla se rompió
        </p>
        <p className="max-w-[38ch] text-sm leading-relaxed text-gray-500 dark:text-gray-400">
          Ya quedó registrado con el detalle técnico: lo puedes ver en Perfil → Análisis → Errores
          recientes.
        </p>
        <div className="mt-2 flex gap-2">
          <button
            type="button"
            onClick={() => this.setState({ error: null })}
            className="inline-flex min-h-[40px] items-center rounded-xl bg-brand-600 dark:bg-brand-200 dark:text-gray-950 px-4 text-sm font-bold text-white transition-colors hover:bg-brand-700 active:scale-[0.97]"
          >
            Reintentar
          </button>
          <button
            type="button"
            onClick={() => window.location.assign("/")}
            className="inline-flex min-h-[40px] items-center rounded-xl bg-white px-4 text-sm font-bold text-gray-700 ring-1 ring-inset ring-gray-200 transition-colors hover:bg-gray-50 dark:bg-gray-900 dark:text-gray-200 dark:ring-gray-700 dark:hover:bg-gray-800"
          >
            Ir al inicio
          </button>
        </div>
        <p className="mt-1 max-w-[44ch] break-words font-mono text-[11px] text-gray-400 dark:text-gray-400">
          {this.state.error.name}: {this.state.error.message}
        </p>
      </div>
    );
  }
}
