import React from "react";
import { DatasetDetail } from "../../components/dataset/DatasetDetail";

export const DatasetsDrawerContent: React.FC = function () {
  return (
    <div className="md:max-w-drawer">
      <DatasetDetail />
    </div>
  );
};
