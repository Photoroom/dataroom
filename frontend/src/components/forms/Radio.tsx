import React from "react";
import { twMerge } from "tailwind-merge";

interface RadioProps {
  label: string | React.ReactNode;
  checked: boolean;
  onChange: (value: boolean) => void;
}

export const Radio: React.FC<RadioProps> = ({ label, checked, onChange }) => {
  return (
    <label
      className={twMerge("flex items-center gap-2 rounded cursor-pointer select-none break-all")}
      onClick={() => onChange(!checked)}
    >
      <span
        className={twMerge(
          "size-4 rounded-full border shrink-0",
          "flex items-center justify-center",
          "border-black/30 dark:border-white/30",
          checked
            ? "bg-teal-400 border-transparent dark:bg-teal-500 dark:border-transparent"
            : "bg-white dark:bg-black/20"
        )}
      >
        {checked && <span className="size-1.5 rounded-full bg-white"></span>}
      </span>
      <span className="text-xs">{label}</span>
    </label>
  );
};
