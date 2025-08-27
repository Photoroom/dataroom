import React from "react";
import defaultValue from "../../utils/defaultValue";
import { formatNumber } from "../../utils/formatNumber";
import { OSImage } from "../../api/client.schemas";
import { FunnelIcon } from "@heroicons/react/24/outline";
import { LoaderSkeleton } from "../common/LoaderSkeleton";
import { Collapsible } from "../common/Collapsible";

interface ImageDetailsProps {
  image?: OSImage;
}

export const ImageDetails: React.FC<ImageDetailsProps> = ({ image }) => {
  return (
    <Collapsible name="details" title="Details">
      <div className="grid grid-cols-2 gap-3">
        <div className="col-span-2">
          <p className="opacity-80">Source</p>
          <p className="font-bold">
            {image ? (
              <span className="flex flex-row items-center gap-1">
                {defaultValue(image?.source)}
                <FunnelIcon className="size-4" />
              </span>
            ) : (
              <LoaderSkeleton />
            )}
          </p>
        </div>
        <div>
          <p className="opacity-80">Width</p>
          <p className="font-bold">
            {image ? defaultValue(formatNumber(image?.width, { decimals: 0 })) : <LoaderSkeleton />}
          </p>
        </div>
        <div>
          <p className="opacity-80">Height</p>
          <p className="font-bold">
            {image ? defaultValue(formatNumber(image?.height, { decimals: 0 })) : <LoaderSkeleton />}
          </p>
        </div>
        <div>
          <p className="opacity-80">Aspect ratio</p>
          <p className="font-bold" title={String(image?.aspect_ratio)}>
            {image ? (
              <>
                {defaultValue(formatNumber(image?.aspect_ratio, { decimals: 6 }))} (
                {defaultValue(image?.aspect_ratio_fraction)})
              </>
            ) : (
              <LoaderSkeleton />
            )}
          </p>
        </div>
        <div>
          <p className="opacity-80">Pixel count</p>
          <p className="font-bold">
            {image ? defaultValue(formatNumber(image?.pixel_count, { decimals: 0 })) : <LoaderSkeleton />}
          </p>
        </div>
      </div>
    </Collapsible>
  );
};
