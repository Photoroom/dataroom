import React, { useEffect, useRef } from "react";
import { twMerge } from "tailwind-merge";
import { CheckIcon } from "@heroicons/react/24/outline";
import { ImageLoading } from "../../components/image/ImageLoading";
import { Image } from "../../components/image/Image";
import { useImageListData } from "../../context/ImageListDataContext";
import { useDragSelect } from "../../context/useDragSelect";
import { Loader } from "../../components/common/Loader";
import { MainContainer } from "../MainContainer";
import { useImageDrawer } from "../../context/ImageDrawerContext";
import { useSidebarConfig } from "./filter/useSidebarConfig";

export const ImageList: React.FC = function () {
  const { isVisible: isSidebarOpen, width: sidebarWidth } = useSidebarConfig();
  const { isDrawerOpen, openDrawer, imageId } = useImageDrawer();
  const {
    images,
    isLoadingImages,
    isLoadingImagesError,
    hasNextPage,
    loadNextPage,
    isLoadingNextPage,
    isLoadingNextPageError,
    mode,
    isSelecting,
    selectedImages,
    toggleSelectedImage,
    addSelectedImages,
    gridColumns,
  } = useImageListData();

  // -------------------- Shared scroll container ref --------------------
  const mainDivRef = useRef<HTMLDivElement>(null);

  // -------------------- Drag-to-select --------------------
  const { selectionRect, onMouseDown, onClickCapture } = useDragSelect({
    containerRef: mainDivRef,
    enabled: isSelecting,
    attribute: "data-image-id",
    onSelect: addSelectedImages,
  });

  // -------------------- Infinite scroll --------------------
  useEffect(() => {
    const div = mainDivRef.current as HTMLDivElement | null;
    let timeoutId: ReturnType<typeof setTimeout>;

    const handleScroll = () => {
      if (
        !div ||
        isLoadingImages ||
        isLoadingImagesError ||
        isLoadingNextPage ||
        isLoadingNextPageError ||
        !hasNextPage
      ) {
        return;
      }

      clearTimeout(timeoutId);

      timeoutId = setTimeout(() => {
        // check if the user has scrolled to the bottom of the div
        if (div.scrollHeight - div.scrollTop - 600 <= div.clientHeight) {
          loadNextPage();
        }
      }, 100);
    };

    handleScroll();
    div?.addEventListener("scroll", handleScroll);

    return () => {
      div?.removeEventListener("scroll", handleScroll);
      clearTimeout(timeoutId);
    };
  }, [
    isLoadingImages,
    isLoadingImagesError,
    isLoadingNextPage,
    isLoadingNextPageError,
    hasNextPage,
    loadNextPage,
    mode,
  ]);

  // -------------------- Render --------------------
  return (
    <MainContainer
      ref={mainDivRef}
      isDrawerOpen={isDrawerOpen}
      isSidebarOpen={isSidebarOpen}
      sidebarWidth={sidebarWidth}
      hasSecondToolbarRow
    >
      {/* Selection rectangle — position:absolute so it lives in content space and scrolls with the container */}
      {selectionRect && (
        <div
          style={{
            position: "absolute",
            left: selectionRect.left,
            top: selectionRect.top,
            width: selectionRect.width,
            height: selectionRect.height,
            pointerEvents: "none",
            zIndex: 50,
          }}
          className="border border-brand-400 bg-brand-400/10"
        />
      )}
      <div
        onMouseDown={onMouseDown}
        onClickCapture={onClickCapture}
        style={{ gridTemplateColumns: `repeat(${gridColumns}, minmax(0, 1fr))` }}
        className={twMerge("grid gap-2 p-2 sm:gap-4 sm:p-4", isSelecting ? "select-none" : "")}
      >
        {/* -------------------- Image list -------------------- */}
        {isLoadingImages
          ? Array(40)
              .fill(null)
              .map((_, index) => <ImageLoading key={index} index={index} />)
          : images.map(image => (
              <Image
                key={image.id}
                image={image}
                selectMode={isSelecting}
                isSelected={selectedImages.includes(image.id)}
                onToggleSelected={isMultiSelect => {
                  toggleSelectedImage(image.id, isMultiSelect);
                }}
              />
            ))}
      </div>
      {/* -------------------- Load more button -------------------- */}
      <div className="flex flex-row items-center justify-center my-10 min-h-12">
        {isLoadingNextPage && <Loader />}
        {!isLoadingNextPage && hasNextPage && (
          <button type="button" className="btn btn-sm btn-outline" onClick={loadNextPage}>
            Load more
          </button>
        )}
        {!isLoadingNextPage && !hasNextPage && <CheckIcon className="size-6 opacity-50" />}
      </div>
      {/* Re-open drawer button when panel is hidden but image is selected */}
      {!isDrawerOpen && imageId && (
        <button
          type="button"
          onClick={openDrawer}
          className="fixed bottom-4 right-4 z-20 px-3 py-2 rounded-lg bg-black/80 text-white text-xs shadow-lg hover:bg-black cursor-pointer dark:bg-white/80 dark:text-black dark:hover:bg-white"
        >
          Show details
        </button>
      )}
    </MainContainer>
  );
};
