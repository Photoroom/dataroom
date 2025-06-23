import React, { createContext, useContext, useEffect, useState } from 'react';
import { useNavigate, useParams, useSearchParams } from 'react-router-dom';
import { Dataset } from '../api/client.schemas';
import { useDatasetsRetrieve } from '../api/client';
import { URLS } from '../urls';
import toast from 'react-hot-toast';

interface DatasetDrawerContextType {
  isDrawerOpen: boolean;
  closeDrawer: () => void;
  datasetSlug: string;
  dataset: Dataset | undefined;
  refetchDataset: () => void;
}

const DatasetDrawerContext = createContext<DatasetDrawerContextType | undefined>(undefined);

export function DatasetDrawerProvider({ children }: { children: React.ReactNode }) {
  const navigate = useNavigate();
  const urlParams = useParams();
  const [isDrawerOpen, setIsDrawerOpen] = useState<boolean>(false);
  
  // the drawer is open if we are on the dataset detail page
  useEffect(() => {
    setIsDrawerOpen(urlParams.datasetSlug !== undefined);
  }, [urlParams]);

  // to close the drawer we just navigate to the dataset list
  const closeDrawer = () => {
    navigate(URLS.DATASET_LIST());
  }

  // -------------------- Dataset detail state --------------------
  const [datasetSlug, setDatasetId] = useState<string>(urlParams.datasetSlug || "");
  const [dataset, setDataset] = useState<Dataset | undefined>(undefined);

  useEffect(() => {
    if (urlParams.datasetSlug && urlParams.datasetSlug !== datasetSlug) {
      setDatasetId(urlParams.datasetSlug);
      setDataset(undefined);
    }
  }, [urlParams, datasetSlug]);

  // -------------------- Fetching dataset detail --------------------
  const { data: datasetDetailResponse, isError: isLoadingDatasetDetailError, refetch: refetchDataset } = useDatasetsRetrieve(datasetSlug);
  
  useEffect(() => {
    if (isLoadingDatasetDetailError) {
      toast.error("Error loading dataset");
    }
  }, [isLoadingDatasetDetailError]);

  useEffect(() => {
    if (datasetDetailResponse) {
      setDataset(datasetDetailResponse);
    }
  }, [datasetDetailResponse]);

  // -------------------- Return --------------------
  return (  
    <DatasetDrawerContext.Provider value={{
      isDrawerOpen,
      closeDrawer,
      datasetSlug,
      dataset,
      refetchDataset,
    }}>
      {children}
    </DatasetDrawerContext.Provider>
  )
}

// hook to use the drawer context
export function useDatasetDrawer() {
  const context = useContext(DatasetDrawerContext);
  if (context === undefined) {
    throw new Error('useDatasetDrawer must be used within a DatasetDrawerProvider');
  }
  return context;
}
