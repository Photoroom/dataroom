import { ImageList } from "./images/ImageList";
import { ImagesSidebarContent } from "./images/ImagesSidebarContent";
import { MainLayout } from "./MainLayout";
import { ImagesDrawerContent } from "./images/ImagesDrawerContent";
import { useImageDrawer } from "../context/ImageDrawerContext";
import { SidebarActiveNav } from "../context/SidebarContext";

export function ImagesLayout() {
  return (
    <MainLayout
      sidebarActiveNav={SidebarActiveNav.IMAGES}
      sidebarContent={<ImagesSidebarContent />}
      drawerContent={<ImagesDrawerContent />}
      useDrawer={useImageDrawer}
    >
      <ImageList />
    </MainLayout>
  );
}
