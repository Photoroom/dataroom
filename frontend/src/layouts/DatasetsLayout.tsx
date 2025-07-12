import { MainLayout } from "./MainLayout";
import { DatasetsSidebarContent } from "./datasets/DatasetsSidebarContent";
import { DatasetsDrawerContent } from "./datasets/DatasetsDrawerContent";
import { Outlet } from "react-router-dom";
import { useDatasetDrawer } from "../context/DatasetDrawerContext";
import { SidebarActiveNav } from "../context/SidebarContext";

export function DatasetsLayout() {
  return (
    <MainLayout
      sidebarActiveNav={SidebarActiveNav.DATASETS}
      sidebarContent={<DatasetsSidebarContent />}
      drawerContent={<DatasetsDrawerContent />}
      useDrawer={useDatasetDrawer}
    >
      <Outlet />
    </MainLayout>
  );
}
