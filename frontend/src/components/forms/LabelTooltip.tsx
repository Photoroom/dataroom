import React, { useState } from "react";
import { useFloating, offset, shift, FloatingPortal } from "@floating-ui/react";
import { Placement } from "@floating-ui/react";
import { twMerge } from "tailwind-merge";
import { QuestionMarkCircleIcon } from "@heroicons/react/24/outline";

interface LabelTooltipProps {
  content: React.ReactNode;
  icon?: React.ReactNode;
  placement?: Placement;
  className?: string;
  tooltipClassName?: string;
}

export function LabelTooltip({
  content,
  icon = (
    <QuestionMarkCircleIcon className="size-4 opacity-40 hover:opacity-100 focus:opacity-100 transition-opacity" />
  ),
  placement = "bottom-start",
  className,
  tooltipClassName,
}: LabelTooltipProps) {
  const [isOpen, setIsOpen] = useState(false);
  const { refs, floatingStyles } = useFloating({
    placement,
    middleware: [offset(3), shift()],
    open: isOpen,
    onOpenChange: setIsOpen,
  });

  return (
    <div className={twMerge("", className)}>
      <div
        ref={refs.setReference}
        className="cursor-help"
        onMouseEnter={() => setIsOpen(true)}
        onMouseLeave={() => setIsOpen(false)}
        onFocus={() => setIsOpen(true)}
        onBlur={() => setIsOpen(false)}
        tabIndex={0}
        role="button"
        aria-label="Information"
      >
        {icon}
      </div>

      {isOpen && (
        <FloatingPortal>
          <div
            ref={refs.setFloating}
            style={floatingStyles}
            className={twMerge(
              "max-w-[260px] min-w-[180px] z-50 p-3 shadow-xl border border-gray-200 rounded-md text-xs text-black bg-white",
              tooltipClassName
            )}
            role="tooltip"
          >
            {content}
          </div>
        </FloatingPortal>
      )}
    </div>
  );
}
