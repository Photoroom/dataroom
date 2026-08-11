import React from "react";
import { useImageDrawer } from "../../context/ImageDrawerContext";
import { useImageListData } from "../../context/ImageListDataContext";
import { ImagePreview } from "../../components/image/ImagePreview";
import { ImageDetails } from "../../components/image/ImageDetails";
import { ImageLatents } from "../../components/image/ImageLatents";
import { ImageAttributes } from "../../components/image/ImageAttributes";
import { ImageRelatedImages } from "../../components/image/ImageRelatedImages";
import { ImageTags } from "../../components/image/ImageTags";
import { ImageDatasets } from "../../components/image/ImageDatasets";
import { ImageMemberships } from "../../components/image/ImageMemberships";
import { PhotoIcon, XMarkIcon, MagnifyingGlassIcon } from "@heroicons/react/24/outline";

export const ImagesDrawerContent: React.FC = function () {
  const { imageId, image, closeDrawer } = useImageDrawer();
  const { setModeSimilarImage } = useImageListData();

  // we need a fixed drawer width to calculate the image height
  const drawerImgWidth = 320 - 12; // drawer width - scrollbar width

  // -------------------- Render --------------------
  return (
    <div className="flex flex-col gap-6 px-4 pt-4 pb-6 md:max-w-drawer text-sm">
      {/* Header with ID and close button */}
      <div className="flex items-start gap-2">
        <div className="flex-1 min-w-0">
          <PhotoIcon className="size-4 shrink-0 inline-block leading-none mr-1.5" />
          <span className="font-bold text-xs font-mono break-all select-all">{imageId}</span>
        </div>
        <button
          type="button"
          onClick={closeDrawer}
          title="Close panel"
          className="shrink-0 p-1 -mt-1 -mr-1 rounded-md opacity-50 hover:opacity-100 hover:bg-black/5 dark:hover:bg-white/5 cursor-pointer transition-colors"
        >
          <XMarkIcon className="size-5" />
        </button>
      </div>
      <ImagePreview image={image} width={drawerImgWidth} />
      {/* Find similar button */}
      <button
        type="button"
        onClick={() => setModeSimilarImage(imageId)}
        className="btn btn-sm btn-outline self-start -mt-3"
      >
        <MagnifyingGlassIcon className="size-4" />
        Find similar
      </button>
      <div className="flex flex-col gap-0 -mx-4 mb-6 border-b border-black/10 dark:border-white/10">
        <ImageDetails image={image} />
        <ImageAttributes image={image} />
        <ImageLatents image={image} />
        <ImageRelatedImages key={imageId} imageId={imageId} />
        <ImageDatasets image={image} />
        <ImageMemberships image={image} />
        <ImageTags image={image} />
      </div>
    </div>
  );
};
