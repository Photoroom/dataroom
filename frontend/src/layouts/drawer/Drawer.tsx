import React from "react";
import { twMerge } from "tailwind-merge";
import { CloseButton } from "../../components/common/CloseButton";

interface DrawerProps {
  useDrawer: () => {
    isDrawerOpen: boolean;
    closeDrawer: () => void;
  };
  children: React.ReactNode;
}


export const Drawer: React.FC<DrawerProps> = function ({ useDrawer, children }) {
  const { isDrawerOpen, closeDrawer } = useDrawer();
  
  return (
    <div className={twMerge(
      "fixed z-20 left-0 bottom-0 right-0",
      "shadow-lg bg-light-100 outline outline-light-300",
      "dark:bg-dark-100 dark:outline-dark-300",
      "flex flex-col",
      "transition-[width,height]",
      "w-full rounded-t-xl",
      "md:left-auto md:top-0",
      "md:rounded-tr-none md:rounded-l-xl",
      isDrawerOpen ? "h-2/3 md:h-full md:w-drawer" : "h-0 md:h-full md:w-0"
    )}
    >
      <CloseButton onClick={closeDrawer} isVisible={isDrawerOpen} />
      {isDrawerOpen && (
        <div className="relative w-full flex-1">
          <div className="absolute left-0 top-0 right-0 bottom-0 overflow-y-auto md:w-drawer">
            {children}
          </div>
        </div>
      )}
    </div>
  );
};
