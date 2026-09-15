"use client";

import { useCallback, useMemo, useState } from "react";

export type AsyncTaskState<T> = {
  /** The request is in flight. */
  running: boolean;
  /** Message to show the user, or null if the last attempt went fine. */
  error: string | null;
  /** What came back, or null if nothing has come back yet. */
  data: T | null;
};

export type AsyncTaskActions<T> = {
  /** Call before awaiting. Clears the previous error — and, unless
   *  `keepData`, the previous result, so a stale answer never sits under a
   *  spinner pretending to be the new one. */
  start: (opts?: { keepData?: boolean }) => void;
  succeed: (data: T | null) => void;
  /** `null` means "it failed but there is nothing worth telling the user" —
   *  a background refresh, say. The previous result is kept either way. */
  fail: (message: string | null) => void;
  reset: () => void;
};

/**
 * The three pieces of state every request on a screen needs: is it running,
 * did it fail, what came back.
 *
 * Perfil declared those three by hand four times over — the CV evaluation,
 * the PDF import, the automatic job search, the CV rewrite — which is twelve
 * `useState` calls and, more to the point, four hand-written copies of the
 * same opening ritual: set running, clear the error, clear the last notice.
 * The copies had already drifted. Three of them cleared the previous notice
 * before starting and one did not, so a failed retry could leave the success
 * message from the previous attempt on screen with an error banner under it.
 *
 * What stays at the call site is the part that really is different at each
 * one: which errors deserve a banner and which are silent (a 404 from the
 * evaluation endpoint just means "nothing saved yet"), and what the result
 * is. That judgement does not belong in a shared hook.
 */
export function useAsyncTask<T>(initialData: T | null = null): [AsyncTaskState<T>, AsyncTaskActions<T>] {
  const [state, setState] = useState<AsyncTaskState<T>>({
    running: false,
    error: null,
    data: initialData,
  });

  const start = useCallback((opts?: { keepData?: boolean }) => {
    setState((prev) => ({
      running: true,
      error: null,
      data: opts?.keepData ? prev.data : null,
    }));
  }, []);

  const succeed = useCallback((data: T | null) => {
    setState({ running: false, error: null, data });
  }, []);

  const fail = useCallback((message: string | null) => {
    setState((prev) => ({ running: false, error: message, data: prev.data }));
  }, []);

  const reset = useCallback(() => {
    setState({ running: false, error: null, data: null });
  }, []);

  // Stable across renders, so callers can list the actions object in a
  // `useCallback`/`useEffect` dependency array and have it mean what it says.
  const actions = useMemo(() => ({ start, succeed, fail, reset }), [start, succeed, fail, reset]);

  return [state, actions];
}

export default useAsyncTask;
