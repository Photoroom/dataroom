import React, { createContext, useContext, useEffect, useState } from "react";
import { useNavigate, useParams, useSearchParams } from "react-router-dom";
import { OSImage } from "../api/client.schemas";
import { useImagesRetrieve } from "../api/client";
import { URLS } from "../urls";
import toast from "react-hot-toast";

interface ImageDrawerContextType {
  isDrawerOpen: boolean;
  closeDrawer: () => void;
  imageId: string;
  image: OSImage | undefined;
  refetchImage: () => void;
}

const ImageDrawerContext = createContext<ImageDrawerContextType | undefined>(undefined);

export function ImageDrawerProvider({ children }: { children: React.ReactNode }) {
  const navigate = useNavigate();
  const urlParams = useParams();
  const [searchParams] = useSearchParams();
  const [isDrawerOpen, setIsDrawerOpen] = useState<boolean>(false);

  // the drawer is open if we are on the image detail page
  useEffect(() => {
    setIsDrawerOpen(urlParams.imageId !== undefined);
  }, [urlParams]);

  // to close the drawer we just navigate to the image list
  const closeDrawer = () => {
    navigate(URLS.IMAGE_LIST(searchParams));
  };

  // -------------------- Image detail state --------------------
  const [imageId, setImageId] = useState<string>(urlParams.imageId || "");
  const [image, setImage] = useState<OSImage | undefined>(undefined);

  useEffect(() => {
    if (urlParams.imageId && urlParams.imageId !== imageId) {
      setImageId(urlParams.imageId);
      setImage(undefined);
    }
  }, [urlParams, imageId]);

  // -------------------- Fetching image detail --------------------
  const detailIncludeFields = "thumbnail,image,latents,attributes,tags,related_images";
  const {
    data: imageDetailResponse,
    isError: isLoadingImageDetailError,
    refetch: refetchImage,
  } = useImagesRetrieve(imageId, {
    include_fields: detailIncludeFields,
  });

  useEffect(() => {
    if (isLoadingImageDetailError) {
      toast.error("Error loading image");
    }
  }, [isLoadingImageDetailError]);

  useEffect(() => {
    if (imageDetailResponse) {
      setImage(imageDetailResponse);
    }
  }, [imageDetailResponse]);

  // -------------------- Return --------------------
  return (
    <ImageDrawerContext.Provider
      value={{
        isDrawerOpen,
        closeDrawer,
        imageId,
        image,
        refetchImage,
      }}
    >
      {children}
    </ImageDrawerContext.Provider>
  );
}

// hook to use the drawer context
export function useImageDrawer() {
  const context = useContext(ImageDrawerContext);
  if (context === undefined) {
    throw new Error("useImageDrawer must be used within a ImageDrawerProvider");
  }
  return context;
}
