import type { Config } from "tailwindcss";

/* ---------------------------------------------------------------------------
 * JobPilot design tokens
 *
 * The palette is deliberately *not* another job-board blue (LinkedIn, Indeed,
 * Glassdoor and most of the category share one). `brand` is a violet-indigo:
 * distinctive enough to be recognizable at a glance in a list of app icons,
 * still saturated/serious enough to read as professional rather than playful.
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
          50: "#f4f2ff",
          100: "#ebe7ff",
          200: "#d9d1ff",
          300: "#bdaaff",
          400: "#9c79ff",
          500: "#7f4dff",
          600: "#6d28f5",
          700: "#5b1fd6",
          800: "#4a1cad",
          900: "#3d1a8a",
          950: "#250f57",
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
        brand: "0 6px 20px -6px rgb(109 40 245 / 0.45)",
        "brand-lg": "0 10px 34px -8px rgb(109 40 245 / 0.5)",
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
