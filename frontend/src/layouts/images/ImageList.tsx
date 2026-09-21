import React, { useEffect, useRef } from "react";
import { twMerge } from "tailwind-merge";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { CheckIcon, NoSymbolIcon } from "@heroicons/react/24/outline";
import { InformationCircleIcon } from "@heroicons/react/20/solid";
import { ImageLoading } from "../../components/image/ImageLoading";
import { Image } from "../../components/image/Image";
import { useImageListData } from "../../context/ImageListDataContext";
import { useDragSelect } from "../../context/useDragSelect";
import { Loader } from "../../components/common/Loader";
import { MainContainer } from "../MainContainer";
import { useImageDrawer } from "../../context/ImageDrawerContext";
import { useSidebarConfig } from "./filter/useSidebarConfig";
import { useClassifierAnnotation } from "../../context/ClassifierAnnotationContext";
import { AnnotationBadge } from "../../components/classifier/AnnotationBadge";
import { ScoreBadge } from "../../components/classifier/ScoreBadge";
import { URLS } from "../../urls";

export const ImageList: React.FC = function () {
  const { isVisible: isSidebarOpen, width: sidebarWidth } = useSidebarConfig();
  // Outside the classifier annotate route this is inert, so tiles render
  // unchanged. While annotating, a click stages a label instead of selecting:
  // once positive, twice negative, three times back to nothing. Taking a saved
  // annotation off the classifier has its own button on the tile.
  const { sideOf, stagedSide, cycle, setMark, isAnnotating } = useClassifierAnnotation();
  const { isDrawerOpen, openDrawer, imageId } = useImageDrawer();
  // While annotating a click labels, so the drawer opens from a tile button instead.
  const { classifierSlug = "", classifierVersion = "" } = useParams();
  const [searchParams] = useSearchParams();
  const navigate = useNavigate();
  // The URL alone does not reopen a closed drawer on the same image.
  const showDetails = (id: string) => {
    navigate(URLS.CLASSIFIER_ANNOTATE_IMAGE(classifierSlug, classifierVersion, id, searchParams));
    openDrawer();
  };
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
    scoredClassifier,
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
      // the staging panel sits where the drawer does, so the grid moves over for it too
      isDrawerOpen={isDrawerOpen || isAnnotating}
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
          : images.map(image => {
              const marked = stagedSide(image.id);
              const isStagedForRemoval = marked === "clear";
              // Only an annotated image has something to remove.
              const canRemove = isAnnotating && sideOf(image) !== null;
              // While a classifier-score filter is active, tiles show that
              // classifier's score. In the annotate workspace both render:
              // filtering by score there IS the active-learning loop, and the
              // score is what you are judging the label against.
              const score = scoredClassifier ? image.classifications?.[scoredClassifier] : undefined;
              return (
                <div key={image.id} className="relative group/tile">
                  <Image
                    image={image}
                    selectMode={isSelecting || isAnnotating}
                    isSelected={isAnnotating ? marked !== null : selectedImages.includes(image.id)}
                    // Staged for removal reads as leaving: the tile drains of
                    // colour rather than gaining another badge to decode.
                    className={isStagedForRemoval ? "opacity-40 grayscale" : undefined}
                    badge={
                      <span className="flex items-center gap-1">
                        <AnnotationBadge side={marked ?? sideOf(image)} pending={marked !== null} />
                        {score !== undefined && <ScoreBadge score={score} />}
                      </span>
                    }
                    onToggleSelected={isMultiSelect => {
                      if (isAnnotating) cycle(image.id);
                      else toggleSelectedImage(image.id, isMultiSelect);
                    }}
                  />
                  {/* Siblings of the tile, not children: the tile is itself a
                      button, and a button inside a button is invalid markup
                      that swallows one of the two clicks. */}
                  {isAnnotating && (
                    <button
                      type="button"
                      onClick={() => showDetails(image.id)}
                      title="Image info"
                      className={twMerge(
                        "absolute z-10 bottom-1.5 right-1.5 p-1 rounded-full cursor-pointer",
                        "bg-black/60 text-white hover:bg-black/80 transition-opacity focus-visible:opacity-100",
                        image.id === imageId ? "opacity-100" : "opacity-0 group-hover/tile:opacity-100"
                      )}
                    >
                      <InformationCircleIcon className="size-4" />
                    </button>
                  )}
                  {canRemove && (
                    <button
                      type="button"
                      onClick={() => setMark(image.id, isStagedForRemoval ? null : "clear")}
                      title={
                        isStagedForRemoval
                          ? "Keep this annotation after all"
                          : "Take this image off the classifier when you save"
                      }
                      className={twMerge(
                        "absolute z-10 top-1.5 right-1.5 p-1 rounded-full cursor-pointer",
                        "bg-black/60 text-white hover:bg-black/80 transition-opacity",
                        // Always visible once staged: a removal you cannot see
                        // without hovering is one you save by accident.
                        isStagedForRemoval ? "opacity-100 bg-neutral-600" : "opacity-0 group-hover/tile:opacity-100"
                      )}
                    >
                      <NoSymbolIcon className="size-3.5" />
                    </button>
                  )}
                </div>
              );
            })}
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
