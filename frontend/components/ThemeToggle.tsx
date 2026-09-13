"use client";

import { useTheme, type ThemePreference } from "@/context/ThemeContext";

const OPTIONS: { value: ThemePreference; label: string; icon: typeof SunIcon }[] = [
  { value: "light", label: "Claro", icon: SunIcon },
  { value: "dark", label: "Oscuro", icon: MoonIcon },
  { value: "system", label: "Sistema", icon: MonitorIcon },
];

/** Light/Dark/System theme switch. `compact` renders a single icon button
 * that cycles through the three options (for tight header space); the
 * default renders a 3-way segmented control. */
export default function ThemeToggle({ compact = false }: { compact?: boolean }) {
  const { theme, setTheme } = useTheme();

  if (compact) {
    // Claro/Oscuro only, at a 44px target. Cycling through three states put
    // "Sistema" between them, and on a phone already in dark mode that looks
    // identical to "Oscuro" — so the first tap appeared to do nothing, on a
    // 32px button. "Seguir al sistema" still lives in the full control below
    // (Perfil → Ajustes).
    const isDark = theme === "dark";
    const next: ThemePreference = isDark ? "light" : "dark";
    const Icon = isDark ? SunIcon : MoonIcon;
    return (
      <button
        type="button"
        onClick={() => setTheme(next)}
        aria-label={isDark ? "Cambiar a tema claro" : "Cambiar a tema oscuro"}
        className="flex h-11 w-11 items-center justify-center rounded-xl border border-gray-200 text-gray-600 transition-colors hover:bg-gray-100 active:scale-95 dark:border-gray-700 dark:text-gray-300 dark:hover:bg-gray-800"
      >
        <Icon className="h-5 w-5" />
      </button>
    );
  }

  return (
    <div
      role="radiogroup"
      aria-label="Tema"
      className="flex items-center gap-0.5 rounded-lg border border-gray-200 p-0.5 dark:border-gray-700"
    >
      {OPTIONS.map((opt) => {
        const Icon = opt.icon;
        const active = theme === opt.value;
        return (
          <button
            key={opt.value}
            type="button"
            role="radio"
            aria-checked={active}
            onClick={() => setTheme(opt.value)}
            title={opt.label}
            aria-label={opt.label}
            className={`flex h-7 w-7 items-center justify-center rounded-md transition-colors ${
              active
                ? "bg-brand-600 text-white"
                : "text-gray-500 hover:bg-gray-100 dark:text-gray-400 dark:hover:bg-gray-800"
            }`}
          >
            <Icon className="h-4 w-4" />
          </button>
        );
      })}
    </div>
  );
}

function SunIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <circle cx="12" cy="12" r="4" />
      <path d="M12 2v2M12 20v2M4.93 4.93l1.41 1.41M17.66 17.66l1.41 1.41M2 12h2M20 12h2M4.93 19.07l1.41-1.41M17.66 6.34l1.41-1.41" />
    </svg>
  );
}

function MoonIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <path d="M21 12.79A9 9 0 1 1 11.21 3 7 7 0 0 0 21 12.79Z" />
    </svg>
  );
}

function MonitorIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
    >
      <rect x="2" y="4" width="20" height="13" rx="2" />
      <path d="M8 21h8M12 17v4" />
    </svg>
  );
}
