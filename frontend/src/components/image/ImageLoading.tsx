import React from "react";

export const ImageLoading: React.FC<{ index?: number }> = ({ index = 0 }) => {
  return <div
    className="w-full aspect-square rounded-lg animate-pulse bg-black/8 dark:bg-white/8"
    style={{
      animationDelay: `${index * 0.05}s`,
    }}
  ></div>;
};
