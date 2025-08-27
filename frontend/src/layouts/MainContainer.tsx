import React, { forwardRef } from "react";
import { useSidebar } from "../context/SidebarContext";
import { twMerge } from "tailwind-merge";

interface MainContainerProps {
  isDrawerOpen: boolean;
  children: React.ReactNode;
}

export const MainContainer = forwardRef<HTMLDivElement, MainContainerProps>(function MainContainer(
  { isDrawerOpen, children },
  ref
) {
  const { isSidebarOpen } = useSidebar();

  return (
    <div
      ref={ref}
      className={twMerge(
        "fixed top-0 left-0 right-0 bottom-0 overflow-y-auto",
        "flex flex-col gap-2 flex-1",
        "transition-[left,right]",
        isSidebarOpen
          ? "top-sidebar-closed md:top-0 md:left-sidebar-open"
          : "top-sidebar-closed md:top-0 md:left-sidebar-closed",
        isDrawerOpen ? "md:right-drawer" : "md:mr-0"
      )}
    >
      {children}
    </div>
  );
});
