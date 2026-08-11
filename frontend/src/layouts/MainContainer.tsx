import React, { forwardRef } from "react";
import { twMerge } from "tailwind-merge";

interface MainContainerProps {
  isDrawerOpen: boolean;
  isSidebarOpen?: boolean;
  // Resizable sidebars (images filter bar) pass their live width; fixed-width
  // sidebars (groups pages, w-60) omit it and keep the static offset.
  sidebarWidth?: number;
  hasSecondToolbarRow?: boolean;
  children: React.ReactNode;
}

export const MainContainer = forwardRef<HTMLDivElement, MainContainerProps>(function MainContainer(
  { isDrawerOpen, isSidebarOpen = false, sidebarWidth, hasSecondToolbarRow = false, children },
  ref
) {
  const resizable = isSidebarOpen && sidebarWidth !== undefined;
  return (
    <div
      ref={ref}
      // CSS var + sm: class instead of an inline `left`: the sidebar is hidden
      // below sm, where the content must stay at left 0.
      style={resizable ? ({ "--sidebar-w": `${sidebarWidth}px` } as React.CSSProperties) : undefined}
      className={twMerge(
        "fixed sm:top-14 left-0 right-0 bottom-0 overflow-y-auto",
        hasSecondToolbarRow ? "top-[5.5rem]" : "top-11",
        "flex flex-col gap-2 flex-1",
        // no left transition while a drag-resize drives the offset
        resizable ? "transition-[right]" : "transition-[left,right]",
        isSidebarOpen && (resizable ? "sm:left-[var(--sidebar-w)]" : "sm:left-60"),
        isDrawerOpen ? "md:right-drawer" : "md:mr-0"
      )}
    >
      {children}
    </div>
  );
});
