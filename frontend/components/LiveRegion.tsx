"use client";

import { createContext, useCallback, useContext, useEffect, useRef, useState } from "react";

/**
 * One polite live region for the whole app.
 *
 * A search for `aria-live` across the frontend used to return zero matches:
 * "Pasaste X · Deshacer", "Guardado en tu pipeline", search results arriving,
 * and every error notice appeared in complete silence for anyone using a
 * screen reader or TalkBack on the Android build. WCAG 2.1 AA, 4.1.3 Status
 * Messages.
 *
 * It matters beyond assistive tech: the undo toast disappears after 8
 * seconds, so a message you did not happen to be looking at is gone.
 *
 * Mounted once in the layout. Anything that changes without the user's focus
 * moving should call `announce()`.
 */

type Announce = (message: string, urgency?: "polite" | "assertive") => void;

const LiveRegionContext = createContext<Announce>(() => {});

export function useAnnounce(): Announce {
  return useContext(LiveRegionContext);
}

export default function LiveRegionProvider({ children }: { children: React.ReactNode }) {
  const [polite, setPolite] = useState("");
  const [assertive, setAssertive] = useState("");
  const clearTimer = useRef<ReturnType<typeof setTimeout> | null>(null);

  const announce = useCallback<Announce>((message, urgency = "polite") => {
    if (!message) return;
    const set = urgency === "assertive" ? setAssertive : setPolite;

    // Blank it first. Screen readers announce a node whose text *changed*, so
    // setting the same string twice in a row (two passes, two "Pasaste") would
    // otherwise say nothing the second time.
    set("");
    requestAnimationFrame(() => set(message));

    if (clearTimer.current) clearTimeout(clearTimer.current);
    clearTimer.current = setTimeout(() => set(""), 6000);
  }, []);

  useEffect(() => {
    return () => {
      if (clearTimer.current) clearTimeout(clearTimer.current);
    };
  }, []);

  return (
    <LiveRegionContext.Provider value={announce}>
      {children}
      {/* sr-only, not hidden: display:none and visibility:hidden remove a node
          from the accessibility tree entirely, which would silence it. */}
      <div aria-live="polite" aria-atomic="true" className="sr-only">
        {polite}
      </div>
      <div role="alert" aria-live="assertive" aria-atomic="true" className="sr-only">
        {assertive}
      </div>
    </LiveRegionContext.Provider>
  );
}
