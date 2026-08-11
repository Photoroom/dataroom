import React from "react";
import ReactDOM from "react-dom";
import { twMerge } from "tailwind-merge";
import { ChevronDownIcon, XMarkIcon } from "@heroicons/react/24/outline";
import { useGroupSelection } from "../../context/GroupSelectionContext";

export const GroupSelectionPanel: React.FC<{
  onMinimize: () => void;
  onAddToDataset: () => void;
  canAddToDataset: boolean;
  selectedTypes: string[];
}> = ({ onMinimize, onAddToDataset, canAddToDataset, selectedTypes }) => {
  const { selectedGroupIds, selectedGroupObjects, toggleSelectedGroup, clearSelectedGroups } = useGroupSelection();

  const selectedString = `${selectedGroupIds.length} group${selectedGroupIds.length === 1 ? "" : "s"}`;
  const mixedTypes = selectedTypes.length > 1;

  return ReactDOM.createPortal(
    <div
      className={twMerge(
        "fixed z-40 bottom-0 left-0 right-0 h-1/2",
        "sm:left-auto sm:top-14 sm:h-auto sm:w-drawer",
        "bg-white dark:bg-dark-100",
        "border-t sm:border-t-0 sm:border-l border-light-300 dark:border-dark-300",
        "shadow-xl flex flex-col rounded-t-xl sm:rounded-t-none sm:rounded-l-xl"
      )}
    >
      {/* Header */}
      <div className="flex items-center justify-between px-4 py-3 border-b border-light-200 dark:border-dark-300 shrink-0">
        <span className="text-sm font-medium">Selection ({selectedString})</span>
        <div className="flex items-center gap-2">
          {selectedGroupIds.length > 0 && (
            <button
              type="button"
              onClick={clearSelectedGroups}
              className="text-xs opacity-50 hover:opacity-100 cursor-pointer"
            >
              Clear all
            </button>
          )}
          <button
            type="button"
            onClick={onMinimize}
            title="Minimize panel"
            className="opacity-50 hover:opacity-100 cursor-pointer"
          >
            <ChevronDownIcon className="size-4" />
          </button>
        </div>
      </div>

      {/* Scrollable group list */}
      <div className="flex-1 overflow-y-auto min-h-0 p-3">
        {selectedGroupIds.length === 0 ? (
          <div className="text-xs text-center py-12 opacity-40">Click groups to add them to your selection.</div>
        ) : (
          <div className="flex flex-col gap-1.5">
            {selectedGroupObjects.map(group => (
              <div key={group.id} className="group flex items-center gap-2 rounded-lg p-1.5 bg-black/4 dark:bg-white/4">
                <div className="size-9 shrink-0 rounded-md overflow-hidden bg-black/8 dark:bg-white/8">
                  {group.cover_thumbnail ? (
                    <img src={group.cover_thumbnail} alt="" loading="lazy" className="w-full h-full object-cover" />
                  ) : null}
                </div>
                <div className="flex flex-col min-w-0 flex-1">
                  <span className="truncate text-xs font-medium" title={group.name}>
                    {group.name}
                  </span>
                  <span className="truncate text-[11px] opacity-50">{group.type}</span>
                </div>
                <button
                  type="button"
                  onClick={() => toggleSelectedGroup(group, false)}
                  title="Remove"
                  className="p-1 rounded-full opacity-40 hover:opacity-100 hover:bg-black/10 dark:hover:bg-white/10 cursor-pointer"
                >
                  <XMarkIcon className="size-3.5" />
                </button>
              </div>
            ))}
          </div>
        )}
      </div>

      {/* Actions */}
      {selectedGroupIds.length > 0 && (
        <div className="flex flex-col gap-2 px-4 py-3 border-t border-light-200 dark:border-dark-300 shrink-0">
          {mixedTypes ? (
            // A dataset holds one group type, so a mixed selection can't be added.
            <p className="text-[11px] leading-snug rounded-md p-2 bg-amber-500/10 text-amber-700 dark:text-amber-300 border border-amber-500/20">
              Groups must all be the same type to add them to a dataset. Selected: {selectedTypes.join(", ")}.
            </p>
          ) : (
            <p className="text-[11px] leading-snug opacity-50">
              Will be added to a <span className="font-medium opacity-100">{selectedTypes[0]}</span> dataset.
            </p>
          )}
          <button
            type="button"
            disabled={!canAddToDataset}
            className="w-full text-xs py-2 rounded-md bg-black text-white hover:bg-black/80 dark:bg-white dark:text-black dark:hover:bg-white/80 disabled:opacity-40 disabled:cursor-not-allowed cursor-pointer"
            onClick={onAddToDataset}
          >
            Add to Dataset
          </button>
        </div>
      )}
    </div>,
    document.body
  );
};
