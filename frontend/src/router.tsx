import { createBrowserRouter } from "react-router-dom";
import { RootLayout } from "./layouts/RootLayout";
import { ImagesLayout } from "./layouts/ImagesLayout";
import { ImageListPage } from "./pages/ImageListPage";
import { ImageDetailPage } from "./pages/ImageDetailPage";
import { ErrorPage } from "./pages/ErrorPage";
import { URLS } from "./urls";
import { DatasetsLayout } from "./layouts/DatasetsLayout";
import { DatasetListPage } from "./pages/DatasetListPage";
import { DatasetDetailPage } from "./pages/DatasetDetailPage";
import { GroupsLayout } from "./layouts/GroupsLayout";
import { GroupListPage } from "./pages/GroupListPage";
import { GroupDetailPage } from "./pages/GroupDetailPage";
import { GroupTypeListPage } from "./pages/GroupTypeListPage";

export const router = createBrowserRouter([
  {
    element: <RootLayout />,
    errorElement: <ErrorPage />,
    children: [
      {
        element: <ImagesLayout />,
        errorElement: <ErrorPage />,
        children: [
          {
            errorElement: <ErrorPage />,
            children: [
              {
                path: URLS.IMAGE_LIST(),
                index: true,
                element: <ImageListPage />,
              },
              {
                path: URLS.IMAGE_DETAIL(":imageId"),
                element: <ImageDetailPage />,
                errorElement: <ErrorPage />,
              },
            ],
          },
        ],
      },
      {
        element: <DatasetsLayout />,
        errorElement: <ErrorPage />,
        children: [
          {
            errorElement: <ErrorPage />,
            children: [
              {
                path: URLS.DATASET_LIST(),
                index: true,
                element: <DatasetListPage />,
              },
              {
                path: URLS.DATASET_DETAIL(":datasetSlug", ":datasetVersion"),
                element: <DatasetDetailPage />,
                errorElement: <ErrorPage />,
              },
            ],
          },
        ],
      },
      {
        element: <GroupsLayout />,
        errorElement: <ErrorPage />,
        children: [
          {
            errorElement: <ErrorPage />,
            children: [
              {
                path: URLS.GROUP_LIST(),
                element: <GroupListPage />,
              },
              {
                path: URLS.GROUP_DETAIL(":groupId"),
                element: <GroupDetailPage />,
                errorElement: <ErrorPage />,
              },
              {
                path: URLS.GROUP_TYPE_LIST(),
                element: <GroupTypeListPage />,
              },
            ],
          },
        ],
      },
    ],
  },
]);
