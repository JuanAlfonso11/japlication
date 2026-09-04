"use client";

import { useEffect, useState } from "react";
import { motion, useMotionValue, useTransform, type PanInfo } from "framer-motion";
import Link from "next/link";
import MatchBreakdown from "@/components/MatchBreakdown";
import ScoreBadge from "@/components/ScoreBadge";
import type { Job } from "@/lib/types";

const SWIPE_THRESHOLD = 120;
const EXIT_DISTANCE = 700;

/** Pure decision logic behind a drag release — pulled out of the
 * component so it's testable without simulating framer-motion's actual
 * pointer/animation lifecycle in jsdom. */
export function resolveDragDecision(offsetX: number): "left" | "right" | null {
  if (offsetX > SWIPE_THRESHOLD) return "right";
  if (offsetX < -SWIPE_THRESHOLD) return "left";
  return null;
}

export default function SwipeCard({
  job,
  onDecide,
  isTop,
  triggerExit,
}: {
  job: Job;
  onDecide: (decision: "left" | "right") => void;
  isTop: boolean;
  /** Set by the parent (e.g. the ✓/✕ buttons or arrow keys) to play the
   * same fly-off exit a drag gesture produces, without requiring a drag. */
  triggerExit?: "left" | "right" | null;
}) {
  const x = useMotionValue(0);
  const rotate = useTransform(x, [-300, 300], [-18, 18]);
  const rightOpacity = useTransform(x, [20, 140], [0, 1]);
  const leftOpacity = useTransform(x, [-140, -20], [1, 0]);
  // Tinder-style color wash across the whole card as it's dragged — green
  // toward "save", rose toward "pass". Purely a lightweight visual cue: a
  // pass never removes the posting, it just stops surfacing on Home (it's
  // still searchable in Discover any time).
  const tint = useTransform(
    x,
    [-220, -20, 0, 20, 220],
    [
      "rgba(244,63,94,0.22)",
      "rgba(244,63,94,0)",
      "rgba(0,0,0,0)",
      "rgba(16,185,129,0)",
      "rgba(16,185,129,0.22)",
    ]
  );
  const [exitX, setExitX] = useState<number | null>(null);
  const [decision, setDecision] = useState<"left" | "right" | null>(null);

  function commitExit(dir: "left" | "right") {
    if (decision) return;
    setDecision(dir);
    setExitX(dir === "right" ? EXIT_DISTANCE : -EXIT_DISTANCE);
  }

  function handleDragEnd(_: unknown, info: PanInfo) {
    const dragDecision = resolveDragDecision(info.offset.x);
    if (dragDecision) commitExit(dragDecision);
  }

  useEffect(() => {
    if (triggerExit) commitExit(triggerExit);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [triggerExit]);

  const match = job.match;

  return (
    <motion.div
      // swipe-drag-surface (globals.css) forces touch-action: none on this
      // element AND every descendant — touch-action isn't inherited by
      // children, so setting it only here would still leave e.g. the job
      // title/description text underneath at the default "auto". A touch
      // starting on that text let the browser claim the gesture for its
      // own native pan/navigation (confirmed via remote devtools: a
      // pointercancel fired moments into the drag) before framer-motion's
      // drag handler ever ran — a swipe that visually "moved the screen"
      // but silently did nothing, since onDragEnd (-> the actual decide()
      // call) never fired. The tradeoff: the card's own description text
      // no longer scrolls via touch while it's the draggable top card —
      // "View full details" still gets you the same content on its own
      // (non-draggable) page.
      className="absolute inset-0 swipe-drag-surface"
      // Once a decision is committed, this card is on its way out — it
      // must stop intercepting touches immediately (not just visually
      // fade), otherwise a still-mounted-but-invisible card can eat the
      // next tap on the ✓/✕ buttons or the card underneath during the
      // brief window before onAnimationComplete removes it from the queue.
      style={{
        x,
        rotate,
        touchAction: "none",
        overscrollBehaviorX: "none",
        pointerEvents: decision ? "none" : "auto",
      }}
      drag={isTop && !decision ? "x" : false}
      dragConstraints={{ left: 0, right: 0 }}
      dragElastic={1}
      onDragEnd={handleDragEnd}
      animate={
        exitX !== null
          ? { x: exitX, opacity: 0, scale: 0.92 }
          : { x: 0, opacity: 1, scale: 1 }
      }
      // A fixed-duration tween for the exit (not spring physics) — a
      // spring's settle time depends on velocity/stiffness/damping
      // interacting, which on some devices resolved fast enough to look
      // like a flash-cut instead of a glide. Snapping back to center
      // (drag released short of the threshold) keeps the springy feel.
      transition={
        exitX !== null
          ? { type: "tween", duration: 0.32, ease: "easeIn" }
          : { type: "spring", stiffness: 300, damping: 30 }
      }
      onAnimationComplete={() => {
        if (decision) onDecide(decision);
      }}
    >
      <div className="relative flex h-full w-full flex-col overflow-hidden rounded-3xl bg-white shadow-lg ring-1 ring-gray-100 dark:bg-gray-900 dark:ring-gray-800">
        <motion.div
          style={{ backgroundColor: tint }}
          className="pointer-events-none absolute inset-0 z-10"
        />
        {isTop && (
          <>
            <motion.div
              style={{ opacity: rightOpacity }}
              className="pointer-events-none absolute right-5 top-5 z-20 rotate-6 rounded-lg border-4 border-emerald-500 px-3 py-1 text-xl font-extrabold text-emerald-500"
            >
              SAVE
            </motion.div>
            <motion.div
              style={{ opacity: leftOpacity }}
              className="pointer-events-none absolute left-5 top-5 z-20 -rotate-6 rounded-lg border-4 border-rose-500 px-3 py-1 text-xl font-extrabold text-rose-500"
            >
              PASS
            </motion.div>
          </>
        )}

        <div className="flex-1 overflow-y-auto p-5">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 className="text-xl font-bold text-gray-900 dark:text-gray-100">{job.title}</h2>
              <p className="text-sm text-gray-600 dark:text-gray-400">{job.company}</p>
              {job.location && <p className="text-xs text-gray-400 dark:text-gray-500">{job.location}</p>}
            </div>
            {match && <ScoreBadge score={match.overall_score} size="lg" />}
          </div>

          {job.skills_required?.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {job.skills_required.slice(0, 8).map((s) => (
                <span
                  key={s.name}
                  className="rounded-full bg-gray-100 px-2.5 py-1 text-xs font-medium text-gray-600 dark:bg-gray-800 dark:text-gray-300"
                >
                  {s.name}
                </span>
              ))}
            </div>
          )}

          {job.requirements?.length > 0 && (
            <div className="mt-4">
              <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-gray-500 dark:text-gray-400">
                Key requirements
              </p>
              <ul className="list-inside list-disc space-y-1 text-sm text-gray-700 dark:text-gray-300">
                {job.requirements.slice(0, 5).map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
            </div>
          )}

          {match && (
            <div className="mt-4 border-t border-gray-100 pt-4 dark:border-gray-800">
              <MatchBreakdown match={match} />
            </div>
          )}

          <Link
            href={`/jobs/${job.id}`}
            onPointerDown={(e) => e.stopPropagation()}
            className="mt-4 inline-block text-xs font-semibold text-brand-600 hover:text-brand-700"
          >
            View full details →
          </Link>
        </div>
      </div>
    </motion.div>
  );
}
