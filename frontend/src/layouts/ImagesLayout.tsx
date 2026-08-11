import { ImageList } from "./images/ImageList";
import { ImagesToolbar, ImagesRightActions } from "./images/ImagesToolbar";
import { MainLayout } from "./MainLayout";
import { ImagesDrawerContent } from "./images/ImagesDrawerContent";
import { useImageDrawer } from "../context/ImageDrawerContext";
import { FilterSidebar } from "./images/filter/FilterSidebar";

export function ImagesLayout() {
  return (
    <MainLayout
      toolbarContent={<ImagesToolbar />}
      rightActions={<ImagesRightActions />}
      drawerContent={<ImagesDrawerContent />}
      useDrawer={useImageDrawer}
      sidebarContent={<FilterSidebar />}
    >
      <ImageList />
    </MainLayout>
  );
}
