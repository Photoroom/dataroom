import React, { useEffect, useState } from "react";
import ReactDOM from "react-dom";
import { useSearchParams } from "react-router-dom";
import { twMerge } from "tailwind-merge";
import { toast } from "react-hot-toast";
import { RectangleStackIcon } from "@heroicons/react/24/outline";
import { useGroupSelection } from "../../context/GroupSelectionContext";
import { GroupSelectionPanel } from "./GroupSelectionPanel";
import Popup from "../../components/common/Popup";
import { AddToDatasetForm } from "../../components/dataset/AddToDatasetForm";
import { consumeAutoSelect } from "../../utils/autoSelect";

// -------------------- Select Button + Panel (renders in the right actions area) --------------------

export const GroupsRightActions: React.FC = () => {
  const { isSelecting, setIsSelecting, selectedGroupIds, selectedGroupObjects } = useGroupSelection();

  const [panelState, setPanelState] = useState<"open" | "minimized" | "closed">("closed");
  const [isAddToDatasetOpen, setIsAddToDatasetOpen] = useState(false);

  const selectedString = `${selectedGroupIds.length} group${selectedGroupIds.length === 1 ? "" : "s"}`;

  // A dataset only accepts groups of its own type, so require a single type.
  const distinctTypes = Array.from(new Set(selectedGroupObjects.map(g => g.type)));
  const groupType = distinctTypes[0] ?? "";
  const mixedTypes = distinctTypes.length > 1;
  const canAddToDataset = selectedGroupIds.length > 0 && !mixedTypes;

  // Selection only makes sense inside one group type (datasets accept a single
  // type), so require the filter bar's type to be picked before entering it.
  const [searchParams] = useSearchParams();
  const selectedType = (searchParams.get("type") ?? "").split(",").filter(Boolean)[0] ?? "";

  // "Add groups" on an empty dataset marks a one-shot flag before navigating
  // here; consume it and arrive with selection mode already open.
  useEffect(() => {
    if (consumeAutoSelect() && selectedType) {
      setIsSelecting(true);
      setPanelState("open");
    }
  }, [selectedType, setIsSelecting]);

  const handleSelectButtonClick = () => {
    if (isSelecting) {
      setIsSelecting(false);
      setPanelState("closed");
    } else if (!selectedType) {
      toast("Pick a group type first");
    } else {
      setIsSelecting(true);
      setPanelState("open");
    }
  };

  return (
    <>
      <button
        type="button"
        title="Select"
        onClick={handleSelectButtonClick}
        className={twMerge(
          "relative flex items-center gap-1.5 px-2 py-1.5 rounded-lg text-xs transition-colors cursor-pointer whitespace-nowrap",
          isSelecting
            ? "bg-black/10 dark:bg-white/10 font-bold"
            : "hover:bg-black/5 dark:hover:bg-white/5 opacity-60 hover:opacity-100"
        )}
      >
        <RectangleStackIcon className="size-4" />
        <span className="hidden sm:inline">Select</span>
        {selectedGroupIds.length > 0 && (
          <span className="absolute -top-1 -right-1 min-w-[1rem] h-4 flex items-center justify-center rounded-full bg-brand-600 text-white text-[10px] font-bold px-1">
            {selectedGroupIds.length}
          </span>
        )}
      </button>

      {/* Selection side panel (full) */}
      {isSelecting && panelState === "open" && (
        <GroupSelectionPanel
          onMinimize={() => setPanelState("minimized")}
          onAddToDataset={() => setIsAddToDatasetOpen(true)}
          canAddToDataset={canAddToDataset}
          selectedTypes={distinctTypes}
        />
      )}

      {/* Selection minimized bar */}
      {isSelecting &&
        panelState === "minimized" &&
        ReactDOM.createPortal(
          <button
            type="button"
            onClick={() => setPanelState("open")}
            className={twMerge(
              "fixed z-40 bottom-0 left-0 right-0 sm:left-auto sm:bottom-auto",
              "sm:top-1/2 sm:-translate-y-1/2 sm:right-0 sm:w-auto",
              "flex items-center justify-center gap-2 px-4 py-3 sm:py-4 sm:px-3 sm:flex-col",
              "bg-white dark:bg-dark-100",
              "border-t sm:border-t-0 sm:border-l border-light-300 dark:border-dark-300",
              "shadow-xl sm:rounded-l-xl cursor-pointer",
              "hover:bg-black/5 dark:hover:bg-white/5 transition-colors"
            )}
          >
            <RectangleStackIcon className="size-4 text-brand-600 dark:text-brand-400" />
            <span className="text-xs font-medium tabular-nums">{selectedGroupIds.length} selected</span>
          </button>,
          document.body
        )}

      {/* Add-to-dataset modal */}
      {isAddToDatasetOpen &&
        ReactDOM.createPortal(
          <Popup onClose={() => setIsAddToDatasetOpen(false)}>
            <h5 className="mb-6">Add {selectedString} to dataset</h5>
            <AddToDatasetForm
              ids={selectedGroupIds}
              noun="group"
              datasetType={groupType}
              onSuccess={() => setIsAddToDatasetOpen(false)}
            />
          </Popup>,
          document.body
        )}
    </>
  );
};
