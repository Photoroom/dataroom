import React, { useEffect, useState } from "react";
import { useDatasetDrawer } from "../context/DatasetDrawerContext";
import { MainContainer } from "../layouts/MainContainer";
import { useDatasetsList } from "../api/client";
import { toast } from "react-hot-toast";
import { Card } from "../components/common/Card";
import { LoaderSkeleton } from "../components/common/LoaderSkeleton";
import { Dataset } from "../api/client.schemas";
import { DatasetCard } from "../components/dataset/DatasetCard";

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
      setLatestDatasets(
        datasets.results.reduce(
          (acc, dataset) => {
            if (dataset.version > (acc[dataset.slug]?.version || 0)) {
              acc[dataset.slug] = dataset;
            }
            return acc;
          },
          {} as Record<string, Dataset>
        )
      );
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
        {Object.values(latestDatasets).map(dataset => {
          return <DatasetCard key={dataset.slug_version} dataset={dataset} />;
        })}
      </div>
    </MainContainer>
  );
};
