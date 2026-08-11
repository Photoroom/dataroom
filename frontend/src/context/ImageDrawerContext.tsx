import React, { createContext, useContext, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { OSImage } from "../api/client.schemas";
import { useImagesRetrieve } from "../api/client";
import toast from "react-hot-toast";

interface ImageDrawerContextType {
  isDrawerOpen: boolean;
  closeDrawer: () => void;
  openDrawer: () => void;
  imageId: string;
  image: OSImage | undefined;
  refetchImage: () => void;
}

const ImageDrawerContext = createContext<ImageDrawerContextType | undefined>(undefined);

export function ImageDrawerProvider({ children }: { children: React.ReactNode }) {
  const urlParams = useParams();

  // Whether we're on an image detail URL
  const hasImageId = !!urlParams.imageId;

  // Local visibility toggle (not URL-driven)
  const [isDrawerVisible, setIsDrawerVisible] = useState(true);

  // Auto-open when imageId changes (user clicked a different image)
  const prevImageIdRef = useRef(urlParams.imageId);
  useEffect(() => {
    if (urlParams.imageId && urlParams.imageId !== prevImageIdRef.current) {
      setIsDrawerVisible(true);
    }
    prevImageIdRef.current = urlParams.imageId;
  }, [urlParams.imageId]);

  // Drawer is open if we have an imageId AND it's not locally hidden
  const isDrawerOpen = hasImageId && isDrawerVisible;

  const closeDrawer = () => {
    setIsDrawerVisible(false);
  };

  const openDrawer = () => {
    setIsDrawerVisible(true);
  };

  // -------------------- Image detail state --------------------
  const imageId = urlParams.imageId || "";

  // -------------------- Fetching image detail --------------------
  const detailIncludeFields = "thumbnail,image,latents,attributes,tags,related_images,datasets";
  const {
    data: image,
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

  // -------------------- Return --------------------
  return (
    <ImageDrawerContext.Provider
      value={{
        isDrawerOpen,
        closeDrawer,
        openDrawer,
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
