"use client";

import { useEffect, useRef, useState } from "react";

/**
 * A piece of UI state that survives leaving the screen.
 *
 * Perfil had two of these written out by hand — the selected tab and the CV
 * language — and each one was a `useState` plus a read effect plus a write
 * effect, six hooks between them saying the same thing twice. The duplication
 * was not just noise: the two copies had already drifted (one validated the
 * stored value, the other was about to not), and a third screen wanting the
 * same behaviour would have copied whichever version it found first.
 *
 * The initial state is the fallback and the stored value is read in an effect,
 * never during render: reading `localStorage` while rendering makes the
 * server-rendered markup and the first client render disagree, which React
 * reports as a hydration error and "fixes" by throwing away the server's HTML.
 *
 * `isValid` is required rather than optional because the value comes from
 * disk, where anything can be: an older build's spelling, a half-written
 * entry, something another tab wrote. Anything unrecognised falls back.
 */
export function useLocalStorageState<T extends string>(
  key: string,
  fallback: T,
  isValid: (value: string) => value is T
): [T, (value: T) => void] {
  const [value, setValue] = useState<T>(fallback);
  const firstWrite = useRef(true);

  useEffect(() => {
    try {
      const stored = window.localStorage.getItem(key);
      if (stored !== null && isValid(stored)) setValue(stored);
    } catch {
      // localStorage unavailable (private mode, blocked site data) — the
      // fallback is a perfectly good answer.
    }
    // `isValid` is a fresh closure on most call sites, so listing it here
    // would re-read on every render and undo the user's choice mid-session.
    // The key is what identifies the entry.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  useEffect(() => {
    // Skipped on the very first pass on purpose. Effects see the values of
    // the render they belong to, so this one would run with the fallback and
    // overwrite the stored entry a microsecond before the read above restores
    // it — the hand-written versions both did that, harmlessly but for
    // nothing. From the second pass on, `value` is either what was restored
    // or what the user just picked, and both are worth writing.
    if (firstWrite.current) {
      firstWrite.current = false;
      return;
    }
    try {
      window.localStorage.setItem(key, value);
    } catch {
      // Non-fatal: the choice just won't outlive this visit.
    }
  }, [key, value]);

  return [value, setValue];
}

export default useLocalStorageState;
