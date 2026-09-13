"use client";

import { useState } from "react";

/** Long prose that starts clamped.
 *
 * The job detail printed the posting's raw description in full: measured on
 * the phone, more than four screens of it sat between the apply block and
 * the tailored CV, which is how "CV a medida" and "Carta de presentación"
 * ended up eight screens down. The text is still all there — it just no
 * longer decides the length of the page. */
export default function CollapsibleText({ text }: { text: string }) {
  const [expanded, setExpanded] = useState(false);
  // The clamp is what actually decides what shows; this only keeps the
  // toggle from appearing under text that already fits.
  const isLong = text.trim().length > 400;

  return (
    <div>
      <p
        className={`whitespace-pre-line text-sm leading-relaxed text-gray-700 dark:text-gray-300 ${
          expanded || !isLong ? "" : "line-clamp-6"
        }`}
      >
        {text}
      </p>
      {isLong && (
        <button
          type="button"
          onClick={() => setExpanded((v) => !v)}
          aria-expanded={expanded}
          className="mt-2 min-h-[36px] text-xs font-bold text-brand-600 hover:underline dark:text-brand-400"
        >
          {expanded ? "Ver menos" : "Ver más"}
        </button>
      )}
    </div>
  );
}
