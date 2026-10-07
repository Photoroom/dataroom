import { Outlet, useLocation } from "react-router-dom";
import { MainLayout } from "./MainLayout";
import { ClassifiersToolbar } from "./classifiers/ClassifiersToolbar";
import { ClassifiersFilterSidebar } from "./classifiers/ClassifiersFilterSidebar";
import { ClassifiersDrawerContent } from "./classifiers/ClassifiersDrawerContent";
import { ClassifierDrawerProvider, useClassifierDrawer } from "../context/ClassifierDrawerContext";
import { URLS } from "../urls";

export function ClassifiersLayout() {
  // The filter rail belongs to the list; a classifier's own page is a document,
  // and only the list offsets its container for the rail.
  const isList = useLocation().pathname === URLS.CLASSIFIER_LIST();

  return (
    <ClassifierDrawerProvider>
      <MainLayout
        toolbarContent={<ClassifiersToolbar />}
        sidebarContent={isList ? <ClassifiersFilterSidebar /> : undefined}
        drawerContent={<ClassifiersDrawerContent />}
        useDrawer={useClassifierDrawer}
      >
        <Outlet />
      </MainLayout>
    </ClassifierDrawerProvider>
  );
}
