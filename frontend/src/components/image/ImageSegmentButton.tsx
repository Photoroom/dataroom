import React from "react";
import { CheckIcon } from "@heroicons/react/24/outline";
import { twMerge } from "tailwind-merge";

export const IMAGE_SEGMENT_COLORS = [
  "#f82553",
  "#6434e9",
  "#343de9",
  "#2ca1e5",
  "#29ee47",
  "#fec20b",
  "#fb6640",
  "#c50ab8",
  "#675112",
  "#085924",
  "#64065a",
];

interface ImageSegmentButtonProps {
  caption: string;
  color?: string;
  selected: boolean;
  highlighted?: boolean;
  onClick: () => void;
  count?: number;
}

export const ImageSegmentButton: React.FC<ImageSegmentButtonProps> = ({
  caption,
  color = "#999",
  selected,
  highlighted,
  onClick,
  count,
}) => {
  return (
    <label
      className={twMerge(
        "flex items-center gap-2 p-2 rounded cursor-pointer select-none",
        highlighted ? "bg-black/5 dark:bg-white/5" : "hover:bg-black/5 dark:hover:bg-white/5"
      )}
      onClick={onClick}
    >
      <div
        className="size-5 rounded relative border-2 flex items-center justify-center shrink-0"
        style={{ borderColor: color, backgroundColor: selected || highlighted ? color : "transparent" }}
      >
        {selected && <CheckIcon className="w-4 h-4 text-white" />}
      </div>
      <span className="text-sm">
        {caption}
        {count !== undefined && <span className="opacity-50"> ({count})</span>}
      </span>
    </label>
  );
};
