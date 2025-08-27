import React from "react";
import { twMerge } from "tailwind-merge";

type ToggleButtonProps = {
  onChange: (checked: boolean) => void;
  label?: string;
  checked?: boolean;
  disabled?: boolean;
};

export function ToggleButton({ onChange, label = "", checked = false, disabled = false }: ToggleButtonProps) {
  const handleChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    onChange(e.target.checked);
  };

  return (
    <label className={twMerge("relative inline-flex items-center cursor-pointer select-none")}>
      <input
        type="checkbox"
        value=""
        checked={checked}
        className="sr-only peer"
        onChange={handleChange}
        disabled={disabled}
      />
      <div
        className={twMerge(
          "w-9 h-5 peer-focus:outline-hidden rounded-full peer",
          "bg-black/25 dark:bg-white/25",
          "after:content-[''] after:absolute after:top-[2px] after:start-[2px] after:bg-white after:rounded-full after:h-4 after:w-4 after:transition-all",
          "peer-checked:after:translate-x-full peer-checked:bg-teal-400 dark:peer-checked:bg-teal-500"
        )}
      ></div>
      {label && <span className="ms-2 text-xs whitespace-nowrap">{label}</span>}
    </label>
  );
}
