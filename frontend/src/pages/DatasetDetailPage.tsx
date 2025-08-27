import React from "react";
import { MainContainer } from "../layouts/MainContainer";
import { useDatasetDrawer } from "../context/DatasetDrawerContext";

export const DatasetDetailPage: React.FC = function () {
  const { isDrawerOpen } = useDatasetDrawer();

  return (
    <MainContainer isDrawerOpen={isDrawerOpen}>
      <div className="w-full p-2">
        <div className="bg-red-500 w-full">Dataset detail</div>
      </div>
    </MainContainer>
  );
};
