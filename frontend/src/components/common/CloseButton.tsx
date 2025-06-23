import React from "react";
import { XMarkIcon } from "@heroicons/react/24/outline";
import { twMerge } from "tailwind-merge";

interface CloseButtonProps {
  onClick: () => void;
  isVisible?: boolean;
  className?: string;
}

export const CloseButton: React.FC<CloseButtonProps> = ({
  onClick,
  isVisible = true,
  className,
}) => {
  return (
    <button
      type="button"
      onClick={onClick}
      title="Close"
      className={twMerge(
        "absolute top-0 right-0 z-20 cursor-pointer size-12",
        "text-black dark:text-white",
        "opacity-40 hover:opacity-100 transition-opacity",
        isVisible ? "block" : "hidden",
        className
      )}
    >
      <XMarkIcon className="size-6 mx-auto" />
    </button>
  );
};
