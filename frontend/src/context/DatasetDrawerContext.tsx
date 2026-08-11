import React, { createContext, useContext, useEffect } from "react";
import { useSearchParams } from "react-router-dom";
import { Dataset } from "../api/client.schemas";
import { useDatasetsRetrieve } from "../api/client";
import toast from "react-hot-toast";

interface DatasetDrawerContextType {
  isDrawerOpen: boolean;
  closeDrawer: () => void;
  datasetSlug: string;
  dataset: Dataset | undefined;
  refetchDataset: () => void;
}

const DatasetDrawerContext = createContext<DatasetDrawerContextType | undefined>(undefined);

// ?dataset=<slug>/<version> drawer, like the group one — list stays mounted.
export function DatasetDrawerProvider({ children }: { children: React.ReactNode }) {
  const [searchParams, setSearchParams] = useSearchParams();
  const datasetSlug = searchParams.get("dataset") || "";
  const isDrawerOpen = !!datasetSlug;

  const closeDrawer = () => {
    setSearchParams(
      prev => {
        const next = new URLSearchParams(prev);
        next.delete("dataset");
        return next;
      },
      { replace: true }
    );
  };

  const {
    data: dataset,
    isError,
    refetch: refetchDataset,
  } = useDatasetsRetrieve(datasetSlug, { query: { enabled: isDrawerOpen } });

  useEffect(() => {
    if (isError) {
      toast.error("Error loading dataset");
    }
  }, [isError]);

  return (
    <DatasetDrawerContext.Provider value={{ isDrawerOpen, closeDrawer, datasetSlug, dataset, refetchDataset }}>
      {children}
    </DatasetDrawerContext.Provider>
  );
}

export function useDatasetDrawer() {
  const context = useContext(DatasetDrawerContext);
  if (context === undefined) {
    throw new Error("useDatasetDrawer must be used within a DatasetDrawerProvider");
  }
  return context;
}
