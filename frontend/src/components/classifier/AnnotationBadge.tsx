import React from "react";
import { twMerge } from "tailwind-merge";
import { AnnotatedSide, StagedMark } from "../../context/ClassifierAnnotationContext";

const MARKS: Record<StagedMark, { className: string; glyph: string; staged: string; saved: string }> = {
  positive: {
    className: "bg-emerald-600",
    glyph: "+",
    staged: "Staged as positive, not saved yet",
    saved: "Already a positive annotation",
  },
  negative: {
    className: "bg-rose-600",
    glyph: "−",
    staged: "Staged as negative, not saved yet",
    saved: "Already a negative annotation",
  },
  clear: {
    className: "bg-neutral-500",
    glyph: "⊘",
    staged: "Staged for removal: this image stops being annotated on either side",
    saved: "",
  },
};

/** The side an image is on: saved (solid) or staged by a click (ringed).
 *
 * Staged is drawn differently on purpose: a click is a decision you have not
 * committed yet, and it should not look identical to what is already stored.
 * ``clear`` is only ever staged — it is the absence of a label, so there is
 * nothing for it to mean once saved.
 */
export const AnnotationBadge: React.FC<{ side: AnnotatedSide | StagedMark; pending?: boolean }> = ({
  side,
  pending,
}) => {
  if (!side) return null;
  const mark = MARKS[side];
  return (
    <span
      title={pending ? mark.staged : mark.saved}
      className={twMerge(
        "flex items-center justify-center w-5 h-5 rounded-full text-white text-xs font-bold shadow-sm",
        mark.className,
        pending && "ring-2 ring-white dark:ring-dark-100"
      )}
    >
      {mark.glyph}
    </span>
  );
};
