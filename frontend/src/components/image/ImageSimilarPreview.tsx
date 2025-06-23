import React from "react";
import { useImagesSimilarList } from "../../api/client";
import { Image } from "./Image";
import { Collapsible } from "../common/Collapsible";
import { ImageLoading } from "./ImageLoading";
import { useImageListData } from "../../context/ImageListDataContext";

interface ImageSimilarProps {
  imageId: string;
}

export const ImageSimilarPreview: React.FC<ImageSimilarProps> = ({ imageId }) => {
  const { setModeSimilarImage } = useImageListData();
  const { data: similarImages, isLoading: isLoadingSimilarImages, isError: isErrorSimilarImages } = useImagesSimilarList(imageId, {
    fields: "thumbnail,image,similarity",
    number: 6,
  });

  const handleSearchBySimilar = () => {
    setModeSimilarImage(imageId);
  }

  return (
    <Collapsible name="similar" title="Similar images" initialOpen={true}>
      <div className="flex flex-col gap-4">
        <div className="grid grid-cols-2 gap-2 mb-4">
          {isLoadingSimilarImages ? (
            <>
              {
                Array(6).fill(0).map((_, index) => (
                  <ImageLoading key={index} />
                ))
              }
            </>
          ) : isErrorSimilarImages ? (
            <p className="col-span-2 text-sm text-red-800 dark:text-red-400">Error fetching similar images! Does the image have an embedding?</p>
          ) : (
            similarImages?.map((similar) => (
              <Image key={similar.id} image={similar} />
            ))
          )}
        </div>
        <button className="btn btn-sm btn-outline" onClick={handleSearchBySimilar}>Search by similar</button>
      </div>
    </Collapsible>
  );
}; 
