import React from "react";
import { CheckIcon } from "@heroicons/react/20/solid";
import { twMerge } from "tailwind-merge";

interface CheckboxProps {
  label: string | React.ReactNode;
  checked: boolean;
  onChange: (value: boolean) => void;
}

export const Checkbox: React.FC<CheckboxProps> = ({
  label,
  checked,
  onChange,
}) => {
  return (
    <label
      className={twMerge(
        "flex items-center gap-2 rounded cursor-pointer select-none break-all",
      )}
      onClick={() => onChange(!checked)}
    >
      <span className={twMerge(
        "size-4 rounded-sm border shrink-0",
        "flex items-center justify-center",
        "border-black/30 dark:border-white/30",
        checked ? "bg-teal-400 border-transparent dark:bg-teal-500 dark:border-transparent" : "bg-white dark:bg-black/20"
      )}>
        {checked && <CheckIcon className="size-4 text-white dark:text-white" />}
      </span>
      <span className="text-xs">
        {label}
      </span>
    </label>
  );
}

