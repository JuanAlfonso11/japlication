/** True only inside the Android shell, never in a normal browser tab.
 *
 * Read from `window.Capacitor` rather than by importing `@capacitor/core`
 * so this stays safe to call from modules a server render also touches.
 *
 * It exists because the WebView cannot do several things a browser can, and
 * each difference is silent: `blob:` downloads through an anchor do nothing
 * (see downloadFile), and a cross-origin form POST loses its body when the
 * WebView hands a `target=_blank` navigation to the system browser (see the
 * LaTeX export). Both looked like "the button does nothing" until someone
 * tried it on a phone.
 */
export function isNativeApp(): boolean {
  if (typeof window === "undefined") return false;
  const cap = (window as { Capacitor?: { isNativePlatform?: () => boolean } }).Capacitor;
  return typeof cap?.isNativePlatform === "function" ? cap.isNativePlatform() : false;
}
