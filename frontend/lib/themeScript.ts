// Plain module on purpose, NOT inside ThemeContext.tsx: that file is
// "use client", so importing a constant from it into the server-rendered
// app/layout.tsx hands the layout a client *reference* instead of the string.
// The <script> then rendered empty on the server, the theme flashed, and
// React 19 threw hydration error #418 on every page.

export const THEME_STORAGE_KEY = "jobflow_theme";

/** Inlined into <head> (see app/layout.tsx) and run before hydration so the
 * correct theme class is on <html> for the very first paint — otherwise a
 * dark-mode user would see a flash of the light theme while React mounts.
 */
export const THEME_NO_FLASH_SCRIPT = `
(function () {
  try {
    var stored = window.localStorage.getItem("${THEME_STORAGE_KEY}");
    var isDark = stored === "dark" || (stored !== "light" && window.matchMedia("(prefers-color-scheme: dark)").matches);
    var root = document.documentElement;
    if (isDark) root.classList.add("dark");
    root.style.colorScheme = isDark ? "dark" : "light";
  } catch (e) {}
})();
`;
