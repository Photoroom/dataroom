import { MainLayout } from "./MainLayout";
import { DatasetsToolbar } from "./datasets/DatasetsToolbar";
import { DatasetsDrawerContent } from "./datasets/DatasetsDrawerContent";
import { useDatasetDrawer } from "../context/DatasetDrawerContext";
import { Outlet } from "react-router-dom";

export function DatasetsLayout() {
  return (
    <MainLayout
      toolbarContent={<DatasetsToolbar />}
      drawerContent={<DatasetsDrawerContent />}
      useDrawer={useDatasetDrawer}
    >
      <Outlet />
    </MainLayout>
  );
}
