"use client";

import { useCallback, useEffect, useRef, useState } from "react";

const PULL_THRESHOLD = 64; // px of pull needed to trigger a refresh
const MAX_VISUAL_PULL = 100; // beyond this the indicator grows with resistance

/**
 * A manual pull-down-to-refresh gesture, scoped to the page's own scroll
 * position (only arms when already at the very top — this is not a
 * generic "drag anywhere" gesture). Implemented with native touch
 * listeners (not React's onTouch* props) because React batches
 * touchmove/touchstart on a single passive root listener — calling
 * preventDefault() from a synthetic handler silently does nothing, so a
 * native `{ passive: false }` listener is the only way to actually stop
 * the browser's own scroll/overscroll from fighting this gesture. See
 * globals.css's `.swipe-drag-surface` comment for the same lesson learned
 * the hard way on the swipe cards themselves.
 *
 * `ignoreSelector` lets a touch that starts inside a specific subtree
 * (e.g. the swipe card, which has its own horizontal drag gesture) skip
 * this entirely — a touch on the card should never fight the card's own
 * gesture handling, or double-trigger both.
 */
export default function PullToRefresh({
  onRefresh,
  ignoreSelector,
  children,
}: {
  onRefresh: () => Promise<void>;
  ignoreSelector?: string;
  children: React.ReactNode;
}) {
  const containerRef = useRef<HTMLDivElement>(null);
  const startY = useRef<number | null>(null);
  const active = useRef(false);
  const [pull, setPull] = useState(0);
  const [refreshing, setRefreshing] = useState(false);
  const refreshingRef = useRef(false);

  const runRefresh = useCallback(
    async (finalPull: number) => {
      refreshingRef.current = true;
      setRefreshing(true);
      setPull(finalPull);
      try {
        await onRefresh();
      } finally {
        refreshingRef.current = false;
        setRefreshing(false);
        setPull(0);
      }
    },
    [onRefresh]
  );

  useEffect(() => {
    const el = containerRef.current;
    if (!el) return;

    function onTouchStart(e: TouchEvent) {
      if (refreshingRef.current) return;
      if (window.scrollY > 0) return;
      if (ignoreSelector && (e.target as Element)?.closest?.(ignoreSelector)) return;
      startY.current = e.touches[0].clientY;
      active.current = true;
    }

    function onTouchMove(e: TouchEvent) {
      if (!active.current || startY.current === null || refreshingRef.current) return;
      const delta = e.touches[0].clientY - startY.current;
      if (delta <= 0 || window.scrollY > 0) {
        active.current = false;
        setPull(0);
        return;
      }
      e.preventDefault();
      const damped = delta < MAX_VISUAL_PULL ? delta : MAX_VISUAL_PULL + (delta - MAX_VISUAL_PULL) * 0.2;
      setPull(damped);
    }

    function onTouchEnd() {
      if (!active.current) return;
      active.current = false;
      startY.current = null;
      setPull((current) => {
        if (current >= PULL_THRESHOLD) {
          runRefresh(PULL_THRESHOLD);
          return current;
        }
        return 0;
      });
    }

    el.addEventListener("touchstart", onTouchStart, { passive: true });
    el.addEventListener("touchmove", onTouchMove, { passive: false });
    el.addEventListener("touchend", onTouchEnd, { passive: true });
    el.addEventListener("touchcancel", onTouchEnd, { passive: true });
    return () => {
      el.removeEventListener("touchstart", onTouchStart);
      el.removeEventListener("touchmove", onTouchMove);
      el.removeEventListener("touchend", onTouchEnd);
      el.removeEventListener("touchcancel", onTouchEnd);
    };
  }, [ignoreSelector, runRefresh]);

  const indicatorOpacity = refreshing ? 1 : Math.min(pull / PULL_THRESHOLD, 1);

  return (
    <div ref={containerRef}>
      <div
        className="flex items-center justify-center overflow-hidden"
        style={{ height: pull, transition: active.current ? "none" : "height 200ms ease-out" }}
      >
        <div
          className="flex items-center gap-1.5 text-xs font-medium text-gray-400 dark:text-gray-500"
          style={{ opacity: indicatorOpacity }}
        >
          <span
            className={refreshing ? "animate-spin" : ""}
            style={!refreshing ? { display: "inline-block", transform: `rotate(${pull * 3}deg)` } : undefined}
          >
            🔄
          </span>
          {refreshing
            ? "Buscando nuevas vacantes…"
            : pull >= PULL_THRESHOLD
              ? "Suelta para actualizar"
              : "Desliza hacia abajo para buscar más"}
        </div>
      </div>
      {children}
    </div>
  );
}
