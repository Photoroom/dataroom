import { ReactNode } from "react";
import { ImageListDataProvider } from "../context/ImageListDataContext";
import { CollapsibleProvider } from "../context/CollapsibleContext";
import { ImageDrawerProvider } from "../context/ImageDrawerContext";
import { GroupDrawerProvider } from "../context/GroupDrawerContext";
import { DatasetDrawerProvider } from "../context/DatasetDrawerContext";
import { SidebarConfigProvider } from "./images/filter/useSidebarConfig";
import { TopBar } from "./TopBar";
import { Drawer } from "./drawer/Drawer";

interface MainLayoutProps {
  toolbarContent?: ReactNode;
  rightActions?: ReactNode;
  drawerContent?: ReactNode;
  useDrawer?: () => { isDrawerOpen: boolean; closeDrawer: () => void };
  sidebarContent?: ReactNode;
  children: ReactNode;
}

export function MainLayout({
  toolbarContent,
  rightActions,
  drawerContent,
  useDrawer,
  sidebarContent,
  children,
}: MainLayoutProps) {
  return (
    <SidebarConfigProvider>
      <ImageListDataProvider>
        <ImageDrawerProvider>
          <GroupDrawerProvider>
            <DatasetDrawerProvider>
              <CollapsibleProvider>
                <TopBar rightActions={rightActions}>{toolbarContent}</TopBar>
                {sidebarContent}
                {children}
                {drawerContent && useDrawer && <Drawer useDrawer={useDrawer}>{drawerContent}</Drawer>}
              </CollapsibleProvider>
            </DatasetDrawerProvider>
          </GroupDrawerProvider>
        </ImageDrawerProvider>
      </ImageListDataProvider>
    </SidebarConfigProvider>
  );
}
