import React, { useEffect, useRef } from "react";
import { twMerge } from "tailwind-merge";
import { CheckIcon } from "@heroicons/react/24/outline";
import { ImageLoading } from "../../components/image/ImageLoading";
import { Image } from "../../components/image/Image";
import { ImageListMode, useImageListData } from "../../context/ImageListDataContext";
import { Loader } from "../../components/common/Loader";
import { MainContainer } from "../MainContainer";
import { useImageDrawer } from "../../context/ImageDrawerContext";


export const ImageList: React.FC = function () {
  const { isDrawerOpen } = useImageDrawer();
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
  } = useImageListData();

  // -------------------- Infinite scroll --------------------
  const mainDivRef = useRef(null);
  useEffect(() => {
    const div = mainDivRef.current as HTMLDivElement | null;
    let timeoutId: NodeJS.Timeout;

    const handleScroll = () => {
      if (
        !div ||
        isLoadingImages || isLoadingImagesError || isLoadingNextPage || isLoadingNextPageError || 
        !hasNextPage || mode === ImageListMode.RANDOM
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
    }
    
    handleScroll();
    div?.addEventListener('scroll', handleScroll);

    return () => {
      div?.removeEventListener('scroll', handleScroll);
      clearTimeout(timeoutId);
    }
  }, [isLoadingImages, isLoadingImagesError, isLoadingNextPage, isLoadingNextPageError, hasNextPage, loadNextPage, mode]);

  // -------------------- Render --------------------
  return (
    <MainContainer ref={mainDivRef} isDrawerOpen={isDrawerOpen}>
      <div className={twMerge(
        "grid grid-cols-2 sm:grid-cols-3 md:grid-cols-4 lg:grid-cols-5 xl:grid-cols-6 2xl:grid-cols-7 gap-4 p-4",
      )}>
        {/* -------------------- Image list -------------------- */}
        {
          isLoadingImages ? (
            Array(40).fill(null).map((_, index) => (
              <ImageLoading key={index} index={index} />
            ))
          ) : (
            images.map((image) => (
              <Image
                key={image.id}
                image={image}
                selectMode={isSelecting}
                isSelected={selectedImages.includes(image.id)}
                onToggleSelected={(isMultiSelect) => { toggleSelectedImage(image.id, isMultiSelect) }}
              />
            ))
          )
        }
      </div>
      {/* -------------------- Load more button -------------------- */}
      <div className="flex flex-row items-center justify-center my-10 min-h-12">
        {isLoadingNextPage && <Loader />}
        {
          (!isLoadingNextPage && (hasNextPage || mode === ImageListMode.RANDOM)) && 
          <button type="button" className="btn btn-sm btn-outline" onClick={loadNextPage}>Load more{mode === ImageListMode.RANDOM && " randomly"}</button>
        }
        {(!isLoadingNextPage && !hasNextPage && mode !== ImageListMode.RANDOM) && <CheckIcon className="size-6 opacity-50" />}
      </div>
    </MainContainer>
  )
}
