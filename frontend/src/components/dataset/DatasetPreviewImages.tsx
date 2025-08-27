import React from "react";
import { useDatasetsImagesRetrieve } from "../../api/client";

interface DatasetPreviewImagesProps {
  slugVersion: string;
  maxImages?: number;
}

export const DatasetPreviewImages: React.FC<DatasetPreviewImagesProps> = function ({ slugVersion, maxImages = 4 }) {
  const { data: dataset } = useDatasetsImagesRetrieve(slugVersion);

  return dataset?.preview_images.slice(0, maxImages).map((image, i) => {
    return (
      <span
        key={i}
        className="block w-full h-full bg-cover bg-center"
        style={{ backgroundImage: `url(${image.thumbnail || image.image})` }}
      ></span>
    );
  });
};
