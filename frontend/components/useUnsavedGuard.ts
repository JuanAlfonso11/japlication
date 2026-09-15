"use client";

import { useEffect } from "react";

/**
 * Warns before losing unsaved form work.
 *
 * The profile form is the longest in the app and it had no protection at all:
 * a search for `beforeunload` across the frontend returned zero matches. The
 * only warning was a small amber "Cambios sin guardar" line at the top of the
 * page. On a phone the bottom nav bar sits directly under the thumb, so one
 * reflex tap on "Inicio" after fifteen minutes of typing achievements threw
 * all of it away silently.
 *
 * Covers both ways out:
 *
 *  - `beforeunload` — reload, closing the tab, following an external link.
 *    The browser shows its own generic dialog; the message is ignored by
 *    every modern browser, which is why none is passed.
 *
 *  - a capture-phase click on any in-app link — Next.js client navigation
 *    never fires `beforeunload`, so the bottom nav, the header and every
 *    `<Link>` needed intercepting separately. Capture phase so it runs
 *    before the router's own handler.
 *
 * Deliberately not a custom modal: `confirm()` cannot be missed, cannot be
 * hidden behind the keyboard, and needs no state. This is the one place where
 * interrupting is the point.
 */
export function useUnsavedGuard(dirty: boolean, message: string) {
  useEffect(() => {
    if (!dirty) return;

    function handleBeforeUnload(e: BeforeUnloadEvent) {
      e.preventDefault();
      // Legacy requirement: some browsers only show the dialog if
      // returnValue is set to something.
      e.returnValue = "";
    }

    function handleClickCapture(e: MouseEvent) {
      // Let the user open things in a new tab / window without a prompt —
      // nothing is lost in that case.
      if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) {
        return;
      }
      const anchor = (e.target as HTMLElement | null)?.closest?.("a");
      if (!anchor) return;

      const href = anchor.getAttribute("href");
      if (!href || href.startsWith("#")) return;
      if (anchor.target && anchor.target !== "_self") return;
      if (anchor.hasAttribute("download")) return;

      // Only same-origin, in-app navigation: an external link leaves the page
      // and beforeunload above already covers it.
      const url = new URL(href, window.location.href);
      if (url.origin !== window.location.origin) return;
      if (url.pathname === window.location.pathname) return;

      if (!window.confirm(message)) {
        e.preventDefault();
        e.stopPropagation();
      }
    }

    window.addEventListener("beforeunload", handleBeforeUnload);
    document.addEventListener("click", handleClickCapture, true);
    return () => {
      window.removeEventListener("beforeunload", handleBeforeUnload);
      document.removeEventListener("click", handleClickCapture, true);
    };
  }, [dirty, message]);
}

export default useUnsavedGuard;
