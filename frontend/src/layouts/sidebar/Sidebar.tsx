import React, { useEffect, useRef } from "react";
import { SidebarActiveNav, useSidebar } from "../../context/SidebarContext";
import {
  AdjustmentsVerticalIcon,
  ChevronDownIcon,
  ChevronLeftIcon,
  ChevronRightIcon,
  ChevronUpIcon,
  CircleStackIcon,
  PhotoIcon,
  ShieldCheckIcon,
} from "@heroicons/react/24/outline";
import { twMerge } from "tailwind-merge";
import { Logo } from "../../components/common/Logo";
import { useSettings } from "../../context/SettingsContext";
import { Link } from "react-router-dom";
import { URLS } from "../../urls";

const navLabels = {
  [SidebarActiveNav.IMAGES]: "Images",
  [SidebarActiveNav.DATASETS]: "Datasets",
  [SidebarActiveNav.SETTINGS]: "Settings",
  [SidebarActiveNav.ADMIN]: "Admin",
};

const navIcons = {
  [SidebarActiveNav.IMAGES]: PhotoIcon,
  [SidebarActiveNav.DATASETS]: CircleStackIcon,
  [SidebarActiveNav.SETTINGS]: AdjustmentsVerticalIcon,
  [SidebarActiveNav.ADMIN]: ShieldCheckIcon,
};

const SidebarNavItem: React.FC<{
  navItem: SidebarActiveNav;
  url: string;
  isDirect?: boolean;
  sidebarActiveNav: SidebarActiveNav;
  isSidebarOpen: boolean;
}> = function ({ navItem, url, isDirect, sidebarActiveNav, isSidebarOpen }) {
  const label = navLabels[navItem];
  const Icon = navIcons[navItem];
  const isActive = sidebarActiveNav === navItem;
  const itemClass = twMerge(
    "text-sm flex flex-row items-center gap-2 cursor-pointer px-2 py-2 hover:bg-black/5 dark:hover:bg-white/5",
    !isSidebarOpen && "md:px-0 md:py-3 md:justify-center",
    !isSidebarOpen && isActive && "md:flex",
    isActive && "hidden"
  );
  const iconClass = twMerge("size-4", !isSidebarOpen && "md:block md:size-5 md:self-center");
  const labelClass = twMerge(!isSidebarOpen && "md:hidden");

  if (isDirect) {
    return (
      <a className={itemClass} href={url} title={label}>
        <Icon className={iconClass} />
        <span className={labelClass}>{label}</span>
      </a>
    );
  } else {
    return (
      <Link className={itemClass} to={url} title={label}>
        <Icon className={iconClass} />
        <span className={labelClass}>{label}</span>
      </Link>
    );
  }
};

const SidebarNav: React.FC = function () {
  const { isSidebarOpen, sidebarActiveNav, isSidebarNavOpen, setIsSidebarNavOpen } = useSidebar();
  const { urls, user } = useSettings();
  const activeLabel = navLabels[sidebarActiveNav];

  const dropdownRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const handleClickOutside = (event: MouseEvent) => {
      if (
        isSidebarNavOpen &&
        dropdownRef.current &&
        event.target instanceof Node &&
        !dropdownRef.current.contains(event.target)
      ) {
        setIsSidebarNavOpen(false);
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => {
      document.removeEventListener("mousedown", handleClickOutside);
    };
  }, [isSidebarNavOpen]);

  const navItems = (
    <>
      <SidebarNavItem
        navItem={SidebarActiveNav.IMAGES}
        url={URLS.IMAGE_LIST()}
        sidebarActiveNav={sidebarActiveNav}
        isSidebarOpen={isSidebarOpen}
      />
      <SidebarNavItem
        navItem={SidebarActiveNav.DATASETS}
        url={URLS.DATASET_LIST()}
        sidebarActiveNav={sidebarActiveNav}
        isSidebarOpen={isSidebarOpen}
      />
      <SidebarNavItem
        navItem={SidebarActiveNav.SETTINGS}
        url={URLS.SETTINGS}
        sidebarActiveNav={sidebarActiveNav}
        isSidebarOpen={isSidebarOpen}
      />
      {user.isStaff && urls.adminBackend && (
        <SidebarNavItem
          navItem={SidebarActiveNav.ADMIN}
          url={urls.adminBackend}
          isDirect={true}
          sidebarActiveNav={sidebarActiveNav}
          isSidebarOpen={isSidebarOpen}
        />
      )}
    </>
  );

  return (
    <div ref={dropdownRef} className="relative w-full">
      <button
        type="button"
        onClick={() => {
          setIsSidebarNavOpen(!isSidebarNavOpen);
        }}
        className={twMerge(
          "w-full h-8 px-2 flex flex-row items-center justify-start gap-1 text-lg font-bold cursor-pointer group",
          "rounded-lg border border-transparent hover:border-light-300 dark:hover:border-dark-300",
          isSidebarNavOpen
            ? "!rounded-b-none border-light-300 dark:border-dark-300 !border-b-transparent dark:!border-b-transparent"
            : "",
          !isSidebarOpen && "md:hidden"
        )}
      >
        {activeLabel}
        <ChevronDownIcon className="size-4" />
      </button>
      <div
        className={twMerge(
          "absolute z-10 left-0 top-8 right-0 hidden flex-col gap-0 overflow-hidden rounded-b-lg shadow-lg",
          "bg-white dark:bg-dark-100",
          "border border-light-300 border-t-0 dark:border-dark-300",
          !isSidebarOpen && "md:flex md:relative md:top-auto md:left-auto md:right-auto md:border-0 md:shadow-none",
          isSidebarNavOpen && "flex"
        )}
      >
        {navItems}
      </div>
    </div>
  );
};

interface SidebarProps {
  children: React.ReactNode;
}

export const Sidebar: React.FC<SidebarProps> = function ({ children }) {
  const { isSidebarOpen, toggleSidebar } = useSidebar();

  return (
    <div
      className={twMerge(
        "fixed z-30 left-0 top-0 right-0 shadow-lg bg-light-100 outline outline-light-300",
        "dark:bg-dark-100 dark:outline-dark-300",
        "flex flex-col",
        "transition-[width,height]",
        "w-full rounded-b-xl",
        "md:w-auto md:rounded-b-none",
        "md:right-auto md:bottom-0 md:rounded-r-xl",
        isSidebarOpen ? "h-8/9 md:h-full md:w-sidebar-open" : "h-sidebar-closed md:h-full md:w-sidebar-closed"
      )}
    >
      <div
        className={twMerge(
          "flex flex-row gap-2 items-center justify-center w-full h-16",
          "md:flex-col md:items-center md:justify-start",
          isSidebarOpen ? "pr-2 md:flex-row md:justify-between" : "pr-2 md:pr-0 md:h-auto"
        )}
      >
        <div
          className={twMerge(
            "flex gap-0 items-center justify-start w-full",
            isSidebarOpen ? "md:flex-row" : "md:flex-col"
          )}
        >
          <Logo />
          <SidebarNav />
        </div>
        <div className={twMerge("flex items-center justify-center gap-0", isSidebarOpen ? "flex-row" : "md:flex-col")}>
          <button
            type="button"
            onClick={toggleSidebar}
            className={twMerge(
              "flex flex-row items-center justify-center cursor-pointer size-10",
              "text-black dark:text-white",
              "opacity-40 hover:opacity-100 transition-opacity"
            )}
          >
            {isSidebarOpen ? (
              <>
                <ChevronUpIcon className="size-6 md:hidden" />
                <ChevronLeftIcon className="size-6 hidden md:block" />
              </>
            ) : (
              <>
                <ChevronDownIcon className="size-6 md:hidden" />
                <ChevronRightIcon className="size-6 hidden md:block" />
              </>
            )}
          </button>
        </div>
      </div>
      {isSidebarOpen && (
        <div className="relative w-full flex-1">
          <div className="absolute left-0 top-0 right-0 bottom-0 overflow-y-auto min-w-sidebar-open">{children}</div>
        </div>
      )}
    </div>
  );
};
