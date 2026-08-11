import React from "react";
import { BookmarkIcon, StarIcon } from "@heroicons/react/20/solid";

/**
 * A bookmark with a small star badge in the corner, used to mark saved queries that the
 * current user owns. Accepts the same `className` (sizing/opacity) as a plain heroicon.
 */
export const MyQueryIcon: React.FC<{ className?: string }> = ({ className }) => (
  <span className={`relative inline-flex ${className ?? ""}`}>
    <BookmarkIcon className="size-full" />
    <StarIcon className="absolute -right-1 -top-1 size-2.5 text-amber-500" />
  </span>
);
