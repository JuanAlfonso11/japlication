"use client";

import { useState } from "react";
import { motion, useMotionValue, useTransform, type PanInfo } from "framer-motion";
import Link from "next/link";
import MatchBreakdown from "@/components/MatchBreakdown";
import ScoreBadge from "@/components/ScoreBadge";
import type { Job } from "@/lib/types";

const SWIPE_THRESHOLD = 120;

export default function SwipeCard({
  job,
  onDecide,
  isTop,
}: {
  job: Job;
  onDecide: (decision: "left" | "right") => void;
  isTop: boolean;
}) {
  const x = useMotionValue(0);
  const rotate = useTransform(x, [-300, 300], [-18, 18]);
  const rightOpacity = useTransform(x, [20, 140], [0, 1]);
  const leftOpacity = useTransform(x, [-140, -20], [1, 0]);
  const [exitX, setExitX] = useState<number | null>(null);

  function handleDragEnd(_: unknown, info: PanInfo) {
    if (info.offset.x > SWIPE_THRESHOLD) {
      setExitX(600);
      onDecide("right");
    } else if (info.offset.x < -SWIPE_THRESHOLD) {
      setExitX(-600);
      onDecide("left");
    }
  }

  const match = job.match;

  return (
    <motion.div
      className="absolute inset-0"
      style={{ x, rotate, touchAction: "pan-y" }}
      drag={isTop ? "x" : false}
      dragConstraints={{ left: 0, right: 0 }}
      dragElastic={1}
      onDragEnd={handleDragEnd}
      animate={exitX !== null ? { x: exitX, opacity: 0 } : { x: 0 }}
      transition={{ type: "spring", stiffness: 300, damping: 30 }}
    >
      <div className="flex h-full w-full flex-col overflow-hidden rounded-3xl bg-white shadow-lg ring-1 ring-gray-100">
        {isTop && (
          <>
            <motion.div
              style={{ opacity: rightOpacity }}
              className="pointer-events-none absolute right-5 top-5 z-10 rotate-6 rounded-lg border-4 border-emerald-500 px-3 py-1 text-xl font-extrabold text-emerald-500"
            >
              SAVE
            </motion.div>
            <motion.div
              style={{ opacity: leftOpacity }}
              className="pointer-events-none absolute left-5 top-5 z-10 -rotate-6 rounded-lg border-4 border-rose-500 px-3 py-1 text-xl font-extrabold text-rose-500"
            >
              PASS
            </motion.div>
          </>
        )}

        <div className="flex-1 overflow-y-auto p-5">
          <div className="flex items-start justify-between gap-3">
            <div>
              <h2 className="text-xl font-bold text-gray-900">{job.title}</h2>
              <p className="text-sm text-gray-600">{job.company}</p>
              {job.location && <p className="text-xs text-gray-400">{job.location}</p>}
            </div>
            {match && <ScoreBadge score={match.overall_score} size="lg" />}
          </div>

          {job.skills_required?.length > 0 && (
            <div className="mt-3 flex flex-wrap gap-1.5">
              {job.skills_required.slice(0, 8).map((s) => (
                <span
                  key={s.name}
                  className="rounded-full bg-gray-100 px-2.5 py-1 text-xs font-medium text-gray-600"
                >
                  {s.name}
                </span>
              ))}
            </div>
          )}

          {job.requirements?.length > 0 && (
            <div className="mt-4">
              <p className="mb-1.5 text-xs font-medium uppercase tracking-wide text-gray-500">
                Key requirements
              </p>
              <ul className="list-inside list-disc space-y-1 text-sm text-gray-700">
                {job.requirements.slice(0, 5).map((r, i) => (
                  <li key={i}>{r}</li>
                ))}
              </ul>
            </div>
          )}

          {match && (
            <div className="mt-4 border-t border-gray-100 pt-4">
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
