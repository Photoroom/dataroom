import React from "react";
import { useImagesRelatedList } from "../../api/client";
import { Image } from "./Image";
import { Collapsible } from "../common/Collapsible";
import { ImageLoading } from "./ImageLoading";
import { twMerge } from "tailwind-merge";

interface ImageRelatedImagesProps {
  imageId: string;
}

export const ImageRelatedImages: React.FC<ImageRelatedImagesProps> = ({ imageId }) => {
  const { data: relatedImages, isLoading: isLoadingRelatedImages, isError: isErrorRelatedImages } = useImagesRelatedList(imageId, {
    fields: "thumbnail,image",
  });

  return (
    <Collapsible name="related" title="Related images" initialOpen={true}>
      <div className="flex flex-col gap-2">
        <div className="grid grid-cols-2 gap-2 mb-4">
          {isLoadingRelatedImages ? (
            <>
              {
                Array(2).fill(0).map((_, index) => (
                  <ImageLoading key={index} />
                ))
              }
            </>
          ) : isErrorRelatedImages ? (
            <p className="col-span-2 text-sm text-red-800 dark:text-red-400">Error fetching related images!</p>
          ) : (
            relatedImages && relatedImages.length > 0 ? (
              relatedImages?.map((related) => {
                if (!related.image) {
                  return <div key={related.name} className="relative w-full aspect-square rounded-lg bg-black/8 dark:bg-white/8">
                    <p className="text-xs text-center px-2 py-8">{related.image_id}</p>
                    <span className={twMerge(
                      "block absolute bottom-0 left-0 right-0 overflow-hidden",
                      "bg-gradient-to-t from-black/70 to-black/0",
                      "text-white font-normal text-xs px-1 p-1 rounded-b-lg text-left break-all"
                    )}>{related.name}</span>
                  </div>;
                }
                return <Image key={related.image.id} image={related.image} label={related.name} />;
              })
            ) : (
              <p className="opacity-50">No related images</p>
            )
          )}
        </div>
      </div>
    </Collapsible>
  );
};
