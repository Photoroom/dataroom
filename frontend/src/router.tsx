import { createBrowserRouter, LoaderFunction } from "react-router-dom";
import { RootLayout } from "./layouts/RootLayout";
import { ImagesLayout } from "./layouts/ImagesLayout";
import { ImageListPage } from "./pages/ImageListPage";
import { ImageDetailPage } from "./pages/ImageDetailPage";
import { ErrorPage } from "./pages/ErrorPage";
import { SettingsPage } from "./pages/SettingsPage";
import { PageLayout } from "./layouts/PageLayout";
import { URLS } from "./urls";
import { DatasetsLayout } from "./layouts/DatasetsLayout";
import { DatasetListPage } from "./pages/DatasetListPage";
import { DatasetDetailPage } from "./pages/DatasetDetailPage";


const page = (title?: string, existingLoader?: LoaderFunction) => {
  // Add a loader to set the document title
  const loader: LoaderFunction = async (...args) => {
    document.title = title ? title + " - DataRoom" : "DataRoom";
    
    // If there's an existing loader, call it with the same arguments
    if (existingLoader) {
      return await existingLoader(...args);
    }
    return null;
  };
  
  return { loader };
};

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
                path: URLS.DATASET_DETAIL(":datasetSlug"),
                element: <DatasetDetailPage />,
                errorElement: <ErrorPage />,
              },
            ],
          },
        ],
      },
      {
        element: <PageLayout/>,
        errorElement: <ErrorPage/>,
        children: [
          {
            path: "settings",
            element: <SettingsPage/>,
            ...page("Settings"),
          },
        ]
      }
    ],
  },
]);
