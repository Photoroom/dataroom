import React, { useEffect, useState } from "react";
import { useDatasetDrawer } from "../context/DatasetDrawerContext";
import { MainContainer } from "../layouts/MainContainer";
import { formatNumber } from "../utils/formatNumber";
import { useDatasetsImagesRetrieve, useDatasetsList } from "../api/client";
import { toast } from "react-hot-toast";
import { Card } from "../components/common/Card";
import { LoaderSkeleton } from "../components/common/LoaderSkeleton";
import { TextToParagraphs } from "../components/common/TextToParagraphs";
import { twMerge } from "tailwind-merge";
import { Dataset } from "../api/client.schemas";


interface DatasetPreviewImagesProps {
  slugVersion: string;
  maxImages?: number;
}

const DatasetPreviewImages: React.FC<DatasetPreviewImagesProps> = function ({ slugVersion, maxImages = 4 }) {
  const { data: dataset } = useDatasetsImagesRetrieve(slugVersion);

  return dataset?.preview_images.slice(0, maxImages).map((image, i) => {
    return (
      <span
        key={i}
        className="block w-full h-full bg-cover bg-center"
        style={{backgroundImage: `url(${image.thumbnail || image.image})`}}
      ></span>
    )
  });
}


export const DatasetListPage: React.FC = function () {
  const { isDrawerOpen } = useDatasetDrawer();
  const { data: datasets, isLoading: isLoadingDatasets, isError: isErrorDatasets } = useDatasetsList();
  const [latestDatasets, setLatestDatasets] = useState<Record<string, Dataset>>({});

  useEffect(() => {
    if (isErrorDatasets) {
      toast.error("Error loading datasets");
    }
  }, [isErrorDatasets]);

  useEffect(() => {
    if (datasets?.results) {
      setLatestDatasets(datasets.results.reduce((acc, dataset) => {
        if (dataset.version > (acc[dataset.slug]?.version || 0)) {
          acc[dataset.slug] = dataset;
        }
        return acc;
      }, {} as Record<string, Dataset>));
    }
  }, [datasets]);

  return (
    <MainContainer isDrawerOpen={isDrawerOpen}>
      <div className="flex flex-col gap-4 p-4">
        {isLoadingDatasets && (
          <>
            {Array.from({ length: 4 }).map((_, i) => (
              <Card key={i} className="flex-row">
                <LoaderSkeleton className="size-[200px] shrink-0" />
                <div className="flex flex-col gap-3 p-4 w-full">
                  <LoaderSkeleton className="h-8 w-1/4 min-w-30" />
                  <LoaderSkeleton className="h-6 w-1/2 min-w-40" />
                  <LoaderSkeleton className="h-6 w-1/2 min-w-40" />
                </div>
              </Card>
            ))}
          </>
        )}
        {Object.values(latestDatasets).map((dataset) => {
          return (
            <Card key={dataset.slug} className="flex-col md:flex-row gap-2">
              <div className={twMerge(
                "shrink-0 cursor-pointer relative rounded-lg overflow-hidden grid grid-rows-2 gap-0 bg-black/10",
                "grid-cols-3 min-w-[300px] min-h-[200px]",
              )}>
                <DatasetPreviewImages slugVersion={dataset.slug_version} maxImages={6} />
              </div>
              <div className="flex flex-col gap-2 p-4">
                <div className="flex flex-row gap-2 items-center">
                  <h3 className="text-2xl font-bold">{dataset.name}</h3>
                    <span className="text-[10px] inline font-normal uppercase px-2 py-1 rounded-full bg-black/10 dark:bg-white/10">v{dataset.version}</span>
                    {dataset.is_frozen && <span className="text-[10px] inline font-normal uppercase px-2 py-1 rounded-full bg-cyan-400/40 dark:bg-cyan-600/40">frozen</span>}
                </div>
                <p className="text-sm opacity-70">{formatNumber(dataset.image_count, {decimals: 0})} images</p>
                <TextToParagraphs text={dataset.description} className="text-sm opacity-90" />
              </div>
            </Card>
          )
        })}
      </div>
    </MainContainer>
  );
}
