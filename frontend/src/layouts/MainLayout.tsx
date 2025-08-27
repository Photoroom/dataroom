import { ReactNode } from "react";
import { ImageListDataProvider } from "../context/ImageListDataContext";
import { SidebarProvider, SidebarActiveNav } from "../context/SidebarContext";
import { Drawer } from "./drawer/Drawer";
import { Sidebar } from "./sidebar/Sidebar";
import { CollapsibleProvider } from "../context/CollapsibleContext";
import { ImageDrawerProvider } from "../context/ImageDrawerContext";
import { DatasetDrawerProvider } from "../context/DatasetDrawerContext";

interface MainLayoutProps {
  sidebarActiveNav: SidebarActiveNav;
  sidebarContent: ReactNode;
  drawerContent: ReactNode;
  useDrawer: () => { isDrawerOpen: boolean; closeDrawer: () => void };
  children: ReactNode;
}

export function MainLayout({ sidebarActiveNav, sidebarContent, drawerContent, useDrawer, children }: MainLayoutProps) {
  return (
    <ImageListDataProvider>
      <SidebarProvider initialActiveNav={sidebarActiveNav}>
        <ImageDrawerProvider>
          <DatasetDrawerProvider>
            <CollapsibleProvider>
              <Sidebar>{sidebarContent}</Sidebar>
              {children}
              <Drawer useDrawer={useDrawer}>{drawerContent}</Drawer>
            </CollapsibleProvider>
          </DatasetDrawerProvider>
        </ImageDrawerProvider>
      </SidebarProvider>
    </ImageListDataProvider>
  );
}
