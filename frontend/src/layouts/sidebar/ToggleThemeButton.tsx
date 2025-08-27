import React from "react";
import { useTheme } from "../../context/ThemeContext";
import { SunIcon, MoonIcon } from "@heroicons/react/24/outline";
import { twMerge } from "tailwind-merge";

interface ToggleThemeButtonProps {
  className?: string;
  size?: "sm" | "lg";
}

export const ToggleThemeButton: React.FC<ToggleThemeButtonProps> = ({ className = "", size = "sm" }) => {
  const { theme, toggleTheme } = useTheme();

  return (
    <button
      onClick={toggleTheme}
      className={twMerge(
        "flex items-center justify-center size-8 text-black dark:text-white cursor-pointer",
        "opacity-40 hover:opacity-100 transition-opacity",
        className
      )}
    >
      {theme === "light" ? (
        <SunIcon className={size === "sm" ? "size-4" : "size-6"} />
      ) : (
        <MoonIcon className={size === "sm" ? "size-4" : "size-6"} />
      )}
    </button>
  );
};
