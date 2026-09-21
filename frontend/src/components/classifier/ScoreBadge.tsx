import React from "react";
import { twMerge } from "tailwind-merge";

/** A classifier's score on an image tile, shown while filtering by that
 * classifier's scores. Colour follows the side the score leans to — the same
 * emerald/rose language as the annotation badges — so a grid of results reads
 * at a glance; the number is there for picking a threshold.
 */
export const ScoreBadge: React.FC<{ score: number }> = ({ score }) => (
  <span
    className={twMerge(
      "flex items-center justify-center h-5 px-1.5 rounded-full text-white text-[11px] font-bold tabular-nums select-none",
      score >= 0.5 ? "bg-emerald-600" : "bg-rose-600"
    )}
    title={`Classifier score: ${score}`}
  >
    {score.toFixed(2)}
  </span>
);
