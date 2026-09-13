import type { ReactNode } from "react";
import { Wordmark } from "@/components/ui/Logo";

/** Shared chrome for the signed-out screens (login, register).
 *
 * These are the app's first impression and used to be a bare centered card
 * on a flat gray page — the most generic thing a web app can look like.
 * Two soft brand-colored glows behind the card do most of the work: they
 * cost nothing, read as intentional, and tie the entry screens to the same
 * violet identity as the rest of the product. */
export default function AuthLayout({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle: string;
  children: ReactNode;
}) {
  return (
    <div className="relative flex min-h-dvh items-center justify-center overflow-hidden px-4 py-10">
      {/* Decorative only — hidden from assistive tech, and pointer-events
          are off so they can never intercept a tap on the form. */}
      <div aria-hidden="true" className="pointer-events-none absolute inset-0 overflow-hidden">
        <div className="absolute -left-24 -top-24 h-72 w-72 rounded-full bg-brand-400/25 blur-3xl dark:bg-brand-500/20" />
        <div className="absolute -bottom-32 -right-20 h-80 w-80 rounded-full bg-accent-300/25 blur-3xl dark:bg-brand-700/25" />
      </div>

      <div className="relative w-full max-w-sm animate-slide-up">
        <div className="mb-7 flex flex-col items-center gap-3 text-center">
          <Wordmark markClassName="h-11 w-11" textClassName="text-xl" />
          <div>
            <h1 className="font-display text-2xl font-extrabold tracking-display-tight text-gray-900 dark:text-gray-50">
              {title}
            </h1>
            <p className="mx-auto mt-1.5 max-w-[32ch] text-sm leading-relaxed text-gray-500 dark:text-gray-400">
              {subtitle}
            </p>
          </div>
        </div>

        {/* Solid, not frosted: a translucent card over a blurred backdrop is
            the single most recognizable "AI-generated landing page" texture,
            and here it also dragged the form's own contrast down. */}
        <div className="rounded-3xl bg-white p-6 shadow-card ring-1 ring-gray-200 dark:bg-gray-900 dark:ring-gray-800">
          {children}
        </div>
      </div>
    </div>
  );
}
