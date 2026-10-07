import { useParams } from "react-router-dom";
import { MainLayout } from "./MainLayout";
import { ImageList } from "./images/ImageList";
import { ImagesToolbar } from "./images/ImagesToolbar";
import { ImagesDrawerContent } from "./images/ImagesDrawerContent";
import { useImageDrawer } from "../context/ImageDrawerContext";
import { FilterSidebar } from "./images/filter/FilterSidebar";
import { ClassifierPanel } from "./classifiers/ClassifierPanel";
import { AnnotationStagePanel } from "../components/classifier/AnnotationStagePanel";
import { ClassifierAnnotationProvider } from "../context/ClassifierAnnotationContext";
import { useClassifiersRetrieve } from "../api/client";

// The annotation workspace: the full image browser (filters, search, drawer)
// with clicks staging labels instead of selecting. Images already in an annotation
// set are badged, so what is left to label is visible while browsing.
export function ClassifierAnnotateLayout() {
  const { classifierSlug, classifierVersion } = useParams();
  const slugVersion = classifierSlug && classifierVersion ? `${classifierSlug}/${classifierVersion}` : "";
  const { data: classifier, refetch } = useClassifiersRetrieve(slugVersion, { query: { enabled: !!slugVersion } });

  const posDatasets = [classifier?.main_pos_dataset, ...(classifier?.extra_pos_datasets ?? [])].filter(
    Boolean
  ) as string[];
  const negDatasets = [classifier?.main_neg_dataset, ...(classifier?.extra_neg_datasets ?? [])].filter(
    Boolean
  ) as string[];

  return (
    <ClassifierAnnotationProvider posDatasets={posDatasets} negDatasets={negDatasets} isAnnotating>
      <MainLayout
        toolbarContent={<ImagesToolbar />}
        rightActions={<ClassifierPanel classifier={classifier} />}
        drawerContent={<ImagesDrawerContent />}
        useDrawer={useImageDrawer}
        sidebarContent={<FilterSidebar />}
      >
        <ImageList />
        <AnnotationStagePanel classifier={classifier} onSaved={refetch} />
      </MainLayout>
    </ClassifierAnnotationProvider>
  );
}
