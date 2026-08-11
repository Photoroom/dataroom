import React, { useState } from "react";
import ReactDOM from "react-dom";
import { twMerge } from "tailwind-merge";
import { RectangleStackIcon } from "@heroicons/react/24/outline";
import { FunnelIcon } from "@heroicons/react/24/outline";
import { useImageListData } from "../../context/ImageListDataContext";
import { SearchFilterBar } from "./SearchFilterBar";
import { SelectionSidePanel } from "./SelectionPanel";
import Popup from "../../components/common/Popup";
import { TagsForm } from "../../components/forms/TagsForm";
import { AddToDatasetForm } from "../../components/dataset/AddToDatasetForm";
import { useTagsTagImagesUpdate } from "../../api/client";
import { useSidebarConfig } from "./filter/useSidebarConfig";
import toast from "react-hot-toast";

// -------------------- Main Toolbar (renders in the center toolbar area) --------------------

export const ImagesToolbar: React.FC = () => {
  const { isVisible, toggleVisible } = useSidebarConfig();

  return (
    <>
      <button
        type="button"
        onClick={toggleVisible}
        title={isVisible ? "Hide filter sidebar" : "Show filter sidebar"}
        className={twMerge(
          "hidden sm:flex items-center p-1.5 rounded-lg transition-colors cursor-pointer shrink-0",
          isVisible
            ? "bg-black/10 dark:bg-white/10"
            : "opacity-60 hover:opacity-100 hover:bg-black/5 dark:hover:bg-white/5"
        )}
      >
        <FunnelIcon className="size-4" />
      </button>
      <SearchFilterBar />
    </>
  );
};

// -------------------- Select Button + Panel (renders in the right actions area) --------------------

export const ImagesRightActions: React.FC = () => {
  const { isSelecting, setIsSelecting, selectedImages } = useImageListData();

  // Panel state: "open" (full panel), "minimized", or "closed"
  const [panelState, setPanelState] = useState<"open" | "minimized" | "closed">("closed");

  // Modal state lifted here so modals survive panel minimize
  const [isAddTagsOpen, setIsAddTagsOpen] = useState(false);
  const [isAddToDatasetOpen, setIsAddToDatasetOpen] = useState(false);

  const { mutate: tagImages, isPending: isTaggingImages } = useTagsTagImagesUpdate();

  const selectedImagesString = `${selectedImages.length} image${selectedImages.length === 1 ? "" : "s"}`;

  const handleTagsFormSubmit = (tags: string[]) => {
    if (!selectedImages.length) return;
    tagImages(
      { data: { image_ids: selectedImages, tag_names: tags } },
      {
        onSuccess: () => {
          setIsAddTagsOpen(false);
          toast.success(`Added tags to ${selectedImagesString}`);
        },
        onError: () => toast.error("Error adding tags to images"),
      }
    );
  };

  const handleSelectButtonClick = () => {
    if (isSelecting) {
      // Deactivate selection mode, close panel
      setIsSelecting(false);
      setPanelState("closed");
    } else {
      // Activate selection mode, open panel
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
        {selectedImages.length > 0 && (
          <span className="absolute -top-1 -right-1 min-w-[1rem] h-4 flex items-center justify-center rounded-full bg-brand-600 text-white text-[10px] font-bold px-1">
            {selectedImages.length}
          </span>
        )}
      </button>

      {/* Selection side panel (full) */}
      {isSelecting && panelState === "open" && (
        <SelectionSidePanel
          onMinimize={() => setPanelState("minimized")}
          onAddTags={() => setIsAddTagsOpen(true)}
          onAddToDataset={() => setIsAddToDatasetOpen(true)}
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
              // Mobile: bottom bar
              "fixed z-40 bottom-0 left-0 right-0 sm:left-auto sm:bottom-auto",
              // Desktop: right edge, vertically centered
              "sm:top-1/2 sm:-translate-y-1/2 sm:right-0 sm:w-auto",
              "flex items-center justify-center gap-2 px-4 py-3 sm:py-4 sm:px-3 sm:flex-col",
              "bg-white dark:bg-dark-100",
              "border-t sm:border-t-0 sm:border-l border-light-300 dark:border-dark-300",
              "shadow-xl sm:rounded-l-xl cursor-pointer",
              "hover:bg-black/5 dark:hover:bg-white/5 transition-colors"
            )}
          >
            <RectangleStackIcon className="size-4 text-brand-600 dark:text-brand-400" />
            <span className="text-xs font-medium tabular-nums">{selectedImages.length} selected</span>
          </button>,
          document.body
        )}

      {/* Modals */}
      {isAddTagsOpen &&
        ReactDOM.createPortal(
          <Popup onClose={() => setIsAddTagsOpen(false)}>
            <h5 className="mb-6">Add tags to {selectedImagesString}</h5>
            <TagsForm onSubmit={handleTagsFormSubmit} isLoading={isTaggingImages} />
          </Popup>,
          document.body
        )}

      {isAddToDatasetOpen &&
        ReactDOM.createPortal(
          <Popup onClose={() => setIsAddToDatasetOpen(false)}>
            <h5 className="mb-6">Add {selectedImagesString} to dataset</h5>
            <AddToDatasetForm
              ids={selectedImages}
              noun="image"
              datasetType="single_image"
              onSuccess={() => setIsAddToDatasetOpen(false)}
            />
          </Popup>,
          document.body
        )}
    </>
  );
};
