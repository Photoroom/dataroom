import React from "react";
import { formatNumber } from "../../utils/formatNumber";
import { Card } from "../common/Card";
import { twMerge } from "tailwind-merge";
import { Dataset } from "../../api/client.schemas";
import { DatasetPreviewImages } from "./DatasetPreviewImages";
import { TextToParagraphs } from "../common/TextToParagraphs";
import { Link, useSearchParams } from "react-router-dom";
import { URLS } from "../../urls";

interface DatasetCardProps {
  dataset: Dataset;
}

export const DatasetCard: React.FC<DatasetCardProps> = function ({ dataset }) {
  const [searchParams] = useSearchParams();
  const newSearchParams = new URLSearchParams(searchParams);
  newSearchParams.set("datasets", dataset.slug_version);

  return (
    <Card key={dataset.slug} className="flex-col md:flex-row gap-2">
      <Link
        to={URLS.IMAGE_LIST(newSearchParams)}
        className={twMerge(
          "shrink-0 cursor-pointer relative rounded-lg overflow-hidden grid grid-rows-2 gap-0 bg-black/10",
          "grid-cols-3 min-w-[300px] min-h-[200px]"
        )}
      >
        <DatasetPreviewImages slugVersion={dataset.slug_version} maxImages={6} />
      </Link>
      <div className="flex flex-col gap-2 p-4">
        <div className="flex flex-row gap-2 items-center">
          <Link to={URLS.IMAGE_LIST(newSearchParams)}>
            <h3 className="text-2xl font-bold">{dataset.name}</h3>
          </Link>
          <span className="text-[10px] inline font-normal uppercase px-2 py-1 rounded-full bg-black/10 dark:bg-white/10">
            v{dataset.version}
          </span>
          {dataset.is_frozen && (
            <span className="text-[10px] inline font-normal uppercase px-2 py-1 rounded-full bg-cyan-400/40 dark:bg-cyan-600/40">
              frozen
            </span>
          )}
        </div>
        <p className="text-sm opacity-70">{formatNumber(dataset.image_count, { decimals: 0 })} images</p>
        <TextToParagraphs text={dataset.description} className="text-sm opacity-90" />
      </div>
    </Card>
  );
};
