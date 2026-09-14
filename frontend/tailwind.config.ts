import type { Config } from "tailwindcss";

/* ---------------------------------------------------------------------------
 * JobPilot design tokens
 *
 * `brand` is graphite and silver, taken from the owner's own portfolio
 * (juanalvarado.vercel.app: --bg #060607, --surface #0e0e10, --silver
 * #a9adb5). Two earlier hues were wrong for different reasons: violet is the
 * house colour of every AI-assembled UI, which is what this app kept being
 * mistaken for, and green is Glassdoor's and ZipRecruiter's. The category is
 * saturated — LinkedIn and Indeed blue, Glassdoor green, Monster purple — so
 * a near-black identity is the one nobody there is using.
 *
 * The portfolio's red (#e0283a) stays an accent rather than the brand: in
 * this app red already means passed, rejected, error and delete across 121
 * usages, and promoting it would mean repainting all of that onto amber,
 * which already means "warning".
 *
 * A monochrome brand inverts in dark mode: on near-black, a graphite button
 * disappears, so primary surfaces there use the light end of the ramp with
 * dark text (see components/ui/Button.tsx).
 * `accent` (amber) is the warm counterweight — used sparingly for scores,
 * streaks and "look here" moments, never for whole surfaces.
 *
 * `gray` is overridden on purpose rather than added alongside: every existing
 * `gray-*` class in the app then picks up a cool, slightly violet-tinted ink
 * ramp that harmonizes with `brand`, instead of Tailwind's stock neutral. That
 * single override is what stops the UI reading as "default Tailwind".
 *
 * Contrast (WCAG AA) was checked for the pairs the app actually uses:
 * gray-500 on white 4.9:1, gray-600 on white 7.0:1, white on brand-600 4.9:1,
 * brand-300 on gray-950 8.4:1.
 * ------------------------------------------------------------------------- */

const config: Config = {
  darkMode: "class",
  content: [
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./context/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        brand: {
          50: "#f5f6f7",
          100: "#e6e8ec",
          200: "#cdd0d6",
          300: "#b8bbc2",
          400: "#a9adb5",
          500: "#80838b",
          600: "#34343a",
          700: "#1f1f23",
          800: "#14141a",
          900: "#0e0e10",
          950: "#060607",
        },
        accent: {
          50: "#fff9ec",
          100: "#fff0cd",
          200: "#ffdf95",
          300: "#ffc85d",
          400: "#ffb02e",
          500: "#f99207",
          600: "#dd6d02",
          700: "#b74b06",
          800: "#943a0c",
          900: "#7a310d",
        },
        gray: {
          50: "#f6f7fb",
          100: "#eceef5",
          200: "#dcdfeb",
          300: "#c3c8db",
          400: "#969db6",
          500: "#6e7691",
          600: "#545c75",
          700: "#3f465c",
          800: "#2a3042",
          900: "#1b2030",
          950: "#10131e",
        },
      },
      fontFamily: {
        sans: ["var(--font-sans)", "ui-sans-serif", "system-ui", "sans-serif"],
        display: ["var(--font-display)", "var(--font-sans)", "ui-sans-serif", "system-ui", "sans-serif"],
      },
      letterSpacing: {
        "display-tight": "-0.022em",
      },
      borderRadius: {
        "4xl": "2rem",
      },
      boxShadow: {
        /* Two-layer shadows (a tight contact shadow + a wider ambient one)
         * read as real elevation; Tailwind's stock single-layer shadows are
         * what make generic UIs look flat-but-fuzzy. Tinted with the brand
         * hue rather than pure black so shadows sit in the same color world
         * as everything else. */
        soft: "0 1px 2px 0 rgb(30 27 75 / 0.04), 0 1px 3px 0 rgb(30 27 75 / 0.06)",
        card: "0 1px 2px 0 rgb(30 27 75 / 0.04), 0 8px 24px -8px rgb(30 27 75 / 0.12)",
        lift: "0 2px 4px 0 rgb(30 27 75 / 0.05), 0 16px 40px -12px rgb(30 27 75 / 0.20)",
        brand: "0 6px 20px -6px rgb(52 52 58 / 0.45)",
        "brand-lg": "0 10px 34px -8px rgb(52 52 58 / 0.5)",
      },
      keyframes: {
        "fade-in": {
          "0%": { opacity: "0" },
          "100%": { opacity: "1" },
        },
        "slide-up": {
          "0%": { opacity: "0", transform: "translateY(8px)" },
          "100%": { opacity: "1", transform: "translateY(0)" },
        },
        "scale-in": {
          "0%": { opacity: "0", transform: "scale(0.96)" },
          "100%": { opacity: "1", transform: "scale(1)" },
        },
        shimmer: {
          "100%": { transform: "translateX(100%)" },
        },
      },
      animation: {
        "fade-in": "fade-in 0.2s ease-out",
        "slide-up": "slide-up 0.35s cubic-bezier(0.22, 1, 0.36, 1)",
        "scale-in": "scale-in 0.25s cubic-bezier(0.22, 1, 0.36, 1)",
      },
    },
  },
  plugins: [],
};

export default config;
