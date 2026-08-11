import React from "react";
import ReactDOM from "react-dom";
import { twMerge } from "tailwind-merge";
import { ChevronDownIcon, XMarkIcon } from "@heroicons/react/24/outline";
import { useImageListData } from "../../context/ImageListDataContext";
import { Image } from "../../components/image/Image";

export const SelectionSidePanel: React.FC<{
  onMinimize: () => void;
  onAddTags: () => void;
  onAddToDataset: () => void;
}> = ({ onMinimize, onAddTags, onAddToDataset }) => {
  const { selectedImages, selectedImageObjects, toggleSelectedImage, clearSelectedImages } = useImageListData();

  const selectedImagesString = `${selectedImages.length} image${selectedImages.length === 1 ? "" : "s"}`;
  const missingCount = selectedImages.length - selectedImageObjects.length;

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
        <span className="text-sm font-medium">Selection ({selectedImagesString})</span>
        <div className="flex items-center gap-2">
          {selectedImages.length > 0 && (
            <button
              type="button"
              onClick={clearSelectedImages}
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

      {/* Scrollable image grid */}
      <div className="flex-1 overflow-y-auto min-h-0 p-3">
        {selectedImages.length === 0 ? (
          <div className="text-xs text-center py-12 opacity-40">Click images to add them to your selection.</div>
        ) : (
          <>
            <div className="grid grid-cols-5 sm:grid-cols-4 gap-1.5">
              {selectedImageObjects.map(img => (
                <div key={img.id} className="relative group aspect-square">
                  <Image image={img} />
                  <button
                    type="button"
                    onClick={() => toggleSelectedImage(img.id, false)}
                    className={twMerge(
                      "absolute top-0.5 right-0.5 p-0.5 rounded-full",
                      "bg-black/60 text-white opacity-0 group-hover:opacity-100",
                      "transition-opacity cursor-pointer"
                    )}
                  >
                    <XMarkIcon className="size-3" />
                  </button>
                </div>
              ))}
            </div>
            {missingCount > 0 && (
              <div className="text-xs opacity-40 mt-3 text-center">
                +{missingCount} image{missingCount === 1 ? "" : "s"} selected but not yet loaded
              </div>
            )}
          </>
        )}
      </div>

      {/* Actions */}
      {selectedImages.length > 0 && (
        <div className="flex gap-2 px-4 py-3 border-t border-light-200 dark:border-dark-300 shrink-0">
          <button
            type="button"
            className="flex-1 text-xs py-2 rounded-md bg-black text-white hover:bg-black/80 dark:bg-white dark:text-black dark:hover:bg-white/80 cursor-pointer"
            onClick={onAddTags}
          >
            Add Tags
          </button>
          <button
            type="button"
            className="flex-1 text-xs py-2 rounded-md bg-black text-white hover:bg-black/80 dark:bg-white dark:text-black dark:hover:bg-white/80 cursor-pointer"
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
