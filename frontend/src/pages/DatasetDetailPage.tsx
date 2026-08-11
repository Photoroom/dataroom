import React from "react";
import { useParams, useNavigate } from "react-router-dom";
import { useDatasetsRetrieve } from "../api/client";
import { MainContainer } from "../layouts/MainContainer";
import { DatasetDetail } from "../components/dataset/DatasetDetail";
import { URLS } from "../urls";

// Full-page dataset detail at /datasets/:slug/:version (the drawer's "open full
// page" target). Same component as the drawer, fed from the route params.
export const DatasetDetailPage: React.FC = function () {
  const { datasetSlug, datasetVersion } = useParams();
  const navigate = useNavigate();
  const slugVersion = datasetSlug && datasetVersion ? `${datasetSlug}/${datasetVersion}` : "";
  const { data: dataset, refetch } = useDatasetsRetrieve(slugVersion, { query: { enabled: !!slugVersion } });

  return (
    <MainContainer isDrawerOpen={false}>
      <DatasetDetail dataset={dataset} refetch={refetch} onClose={() => navigate(URLS.DATASET_LIST())} onFullPage />
    </MainContainer>
  );
};
