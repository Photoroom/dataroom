import React from "react";
import { twMerge } from "tailwind-merge";

interface LoaderSkeletonProps {
  className?: string;
  style?: React.CSSProperties;
}

export const LoaderSkeleton: React.FC<LoaderSkeletonProps> = ({ className, style }) => {
  return (
    <span
      className={twMerge("block h-6 w-full rounded-sm animate-pulse bg-black/8 dark:bg-white/8", className)}
      style={style}
    ></span>
  );
};
