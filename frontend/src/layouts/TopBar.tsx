import React, { useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { twMerge } from "tailwind-merge";
import { UserCircleIcon } from "@heroicons/react/24/outline";
import { Squares2X2Icon } from "@heroicons/react/24/outline";
import { Logo } from "../components/common/Logo";
import { useImageListData } from "../context/ImageListDataContext";
import { URLS } from "../urls";
import { AccountPanel } from "../components/account/AccountPanel";

// -------------------- Nav Item --------------------

interface NavItemProps {
  label: string;
  to: string;
  isActive: boolean;
}

const NavItem: React.FC<NavItemProps> = ({ label, to, isActive }) => (
  <Link
    className={twMerge(
      "text-sm px-3 py-1.5 rounded-lg transition-colors whitespace-nowrap",
      isActive ? "bg-black/10 dark:bg-white/10 font-bold" : "hover:bg-black/5 dark:hover:bg-white/5"
    )}
    to={to}
  >
    {label}
  </Link>
);

// -------------------- TopBar --------------------

interface TopBarProps {
  children?: React.ReactNode;
  rightActions?: React.ReactNode;
}

export const TopBar: React.FC<TopBarProps> = ({ children, rightActions }) => {
  const location = useLocation();
  const [isAccountOpen, setIsAccountOpen] = useState(false);
  const [isGridSizeOpen, setIsGridSizeOpen] = useState(false);
  const { gridColumns, setGridColumns } = useImageListData();

  const activeNav = location.pathname.startsWith("/datasets")
    ? "datasets"
    : location.pathname.startsWith("/group-types")
      ? "group-types"
      : location.pathname.startsWith("/groups")
        ? "groups"
        : "images";

  // Size control: images grid and the groups/datasets LIST grids. The
  // detail routes (/groups/<id>, /datasets/<slug>/<v>) have their own
  // member layout and don't use gridColumns.
  const isGroupDetail = /^\/groups\/[^/]+/.test(location.pathname);
  const isDatasetDetail = /^\/datasets\/[^/]+/.test(location.pathname);
  const showGridControl =
    activeNav === "images" ||
    (activeNav === "groups" && !isGroupDetail) ||
    (activeNav === "datasets" && !isDatasetDetail);

  return (
    <div
      className={twMerge(
        "fixed z-30 top-0 left-0 right-0",
        "bg-light-100 dark:bg-dark-100",
        "border-b border-light-300 dark:border-dark-300",
        "flex flex-col"
      )}
    >
      {/* Row 1: logo + nav + (desktop: toolbar inline) + icons */}
      <div className="flex flex-row items-center gap-1 sm:gap-2 h-11 sm:h-14 px-1 sm:px-2">
        <Logo className="size-8 sm:size-10 p-0.5 sm:p-1 shrink-0" />

        <nav className="flex flex-row items-center gap-1 shrink-0">
          <NavItem label="Images" to={URLS.IMAGE_LIST()} isActive={activeNav === "images"} />
          <NavItem label="Datasets" to={URLS.DATASET_LIST()} isActive={activeNav === "datasets"} />
          <NavItem label="Groups" to={URLS.GROUP_LIST()} isActive={activeNav === "groups"} />
          <NavItem label="Group types" to={URLS.GROUP_TYPE_LIST()} isActive={activeNav === "group-types"} />
        </nav>

        {/* Toolbar content: always inline on desktop; on mobile, inline for non-images pages */}
        <div
          className={twMerge(
            "flex-1 flex flex-row items-center gap-2 min-w-0",
            activeNav === "images" ? "hidden sm:flex" : "flex"
          )}
        >
          {children}
        </div>

        {/* Mobile spacer (images page only — toolbar goes to row 2) */}
        {activeNav === "images" && <div className="flex-1 sm:hidden" />}

        {/* Right-side icons */}
        <div className="flex items-center gap-2 shrink-0">
          {rightActions}
          {showGridControl && (
            <>
              {/* Mobile: grid icon with dropdown */}
              <div className="relative sm:hidden">
                <button
                  type="button"
                  onClick={() => setIsGridSizeOpen(!isGridSizeOpen)}
                  className={twMerge(
                    "p-1.5 rounded-lg transition-colors cursor-pointer",
                    isGridSizeOpen ? "bg-black/10 dark:bg-white/10" : "opacity-60 hover:opacity-100"
                  )}
                >
                  <Squares2X2Icon className="size-5" />
                </button>
                {isGridSizeOpen && (
                  <div
                    className={twMerge(
                      "absolute right-0 top-full mt-1 z-50",
                      "bg-white dark:bg-dark-100",
                      "border border-light-300 dark:border-dark-300",
                      "rounded-lg shadow-lg overflow-hidden w-28"
                    )}
                  >
                    {[
                      { label: "Large", cols: 3 },
                      { label: "Medium", cols: 5 },
                      { label: "Small", cols: 8 },
                    ].map(opt => (
                      <button
                        key={opt.cols}
                        type="button"
                        onClick={() => {
                          setGridColumns(opt.cols);
                          setIsGridSizeOpen(false);
                        }}
                        className={twMerge(
                          "w-full px-3 py-2 text-left text-sm cursor-pointer",
                          "hover:bg-black/5 dark:hover:bg-white/5",
                          gridColumns === opt.cols && "font-bold"
                        )}
                      >
                        {opt.label}
                      </button>
                    ))}
                  </div>
                )}
              </div>
              {/* Desktop: slider */}
              <div className="hidden sm:flex items-center gap-1.5 opacity-50 hover:opacity-100 transition-opacity">
                <Squares2X2Icon className="size-4 shrink-0" />
                <input
                  type="range"
                  min={3}
                  max={12}
                  value={gridColumns}
                  onChange={e => setGridColumns(Number(e.target.value))}
                  className="slider-visible w-20 cursor-pointer"
                  title={`${gridColumns} columns`}
                />
              </div>
            </>
          )}

          <button
            type="button"
            title="Account"
            onClick={() => setIsAccountOpen(!isAccountOpen)}
            className={twMerge(
              "p-1.5 rounded-lg transition-colors cursor-pointer",
              isAccountOpen
                ? "bg-black/10 dark:bg-white/10"
                : "hover:bg-black/5 dark:hover:bg-white/5 opacity-60 hover:opacity-100"
            )}
          >
            <UserCircleIcon className="size-5" />
          </button>
        </div>
      </div>

      {/* Row 2 (mobile only, images page): filter bar on its own row */}
      {activeNav === "images" && children && (
        <div className="flex sm:hidden flex-row items-center gap-1 px-1 pb-1.5">{children}</div>
      )}

      {/* Account panel */}
      {isAccountOpen && <AccountPanel onClose={() => setIsAccountOpen(false)} />}
    </div>
  );
};
