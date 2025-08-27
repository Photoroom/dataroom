import React from "react";
import { ChevronDownIcon, ChevronUpIcon } from "@heroicons/react/20/solid";
import { twMerge } from "tailwind-merge";
import { useCollapsible } from "../../context/CollapsibleContext";

interface CollapsibleProps {
  name: string;
  title: string;
  children: React.ReactNode;
  initialOpen?: boolean;
  className?: string;
}

export const Collapsible: React.FC<CollapsibleProps> = ({
  name,
  title,
  children,
  initialOpen = true,
  className = "border-t border-black/10 dark:border-white/10",
}) => {
  const { toggleCollapsible, getCollapsibleState } = useCollapsible();
  const isOpen = getCollapsibleState(name, initialOpen);

  return (
    <div className={className}>
      <button
        className="p-4 w-full flex flex-row items-center justify-between group cursor-pointer hover:bg-black/3 dark:hover:bg-white/3 transition-colors"
        onClick={() => {
          toggleCollapsible(name);
        }}
      >
        <h4 className="uppercase text-sm tracking-wide opacity-80 group-hover:opacity-100 transition-opacity">
          {title}
        </h4>
        {isOpen ? (
          <ChevronUpIcon className="size-5 opacity-80 group-hover:opacity-100 transition-opacity" />
        ) : (
          <ChevronDownIcon className="size-5 opacity-80 group-hover:opacity-100 transition-opacity" />
        )}
      </button>
      <div
        className={twMerge(
          "grid transition-all ease-in-out",
          isOpen ? "grid-rows-[1fr] opacity-100" : "grid-rows-[0fr] opacity-0"
        )}
      >
        <div className="overflow-hidden">
          <div className="px-4 pt-2 pb-6">{children}</div>
        </div>
      </div>
    </div>
  );
};
