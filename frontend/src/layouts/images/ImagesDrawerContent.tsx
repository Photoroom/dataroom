import React, { useEffect, useState } from "react";
import { useImageDrawer } from "../../context/ImageDrawerContext";
import { ImagePreview } from "../../components/image/ImagePreview";
import { ImageDetails } from "../../components/image/ImageDetails";
import { ImageSimilarPreview } from "../../components/image/ImageSimilarPreview";
import { ImageLatents } from "../../components/image/ImageLatents";
import { ImageAttributes } from "../../components/image/ImageAttributes";
import { ImageRelatedImages } from "../../components/image/ImageRelatedImages";
import { ImageTags } from "../../components/image/ImageTags";
import { PhotoIcon } from "@heroicons/react/24/outline";

export const ImagesDrawerContent: React.FC = function () {
  const { imageId, image } = useImageDrawer();

  // we need a fixed drawer width to calculate the image height
  const drawerImgWidth = 320 - 12;  // drawer width - scrollbar width

  // -------------------- Render --------------------
  return (
    <div className="flex flex-col gap-6 px-4 pt-4 pb-6 md:max-w-drawer text-sm">
      <div className="mr-8">
        <PhotoIcon className="size-4 shrink-0 inline-block leading-none mr-1.5" />
        <span className="font-bold break-all">{imageId}</span>
      </div>
      <ImagePreview image={image} width={drawerImgWidth} />
      <div className="flex flex-col gap-0 -mx-4 mb-6 border-b border-black/10 dark:border-white/10">
        <ImageDetails image={image} />
        <ImageTags image={image} />
        <ImageAttributes image={image} />
        <ImageLatents image={image} />
        <ImageRelatedImages imageId={imageId} />
        <ImageSimilarPreview imageId={imageId} />
      </div>
    </div>
  );
};
