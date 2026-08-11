import { useCallback, useEffect, useMemo, useState } from "react";
import { OSImage } from "../api/client.schemas";

export function useImageSelection(images: OSImage[]) {
  const [isSelecting, setIsSelecting] = useState(false);
  const [selectedImages, setSelectedImages] = useState<string[]>([]);
  const [lastSelectedImage, setLastSelectedImage] = useState(null as string | null);
  const [lastWasUnselected, setLastWasUnselected] = useState(false);

  const toggleSelectedImage = (imageId: string, isMultiSelect: boolean) => {
    const isAlreadySelected = selectedImages.includes(imageId);

    if (isMultiSelect && lastSelectedImage) {
      const lastSelectedIndex = images.findIndex(image => image.id === lastSelectedImage);
      const currentSelectedIndex = images.findIndex(image => image.id === imageId);
      const start = Math.min(lastSelectedIndex, currentSelectedIndex);
      const end = Math.max(lastSelectedIndex, currentSelectedIndex);
      const selectedIds = images.slice(start, end + 1).map(image => image.id);
      if (lastWasUnselected) {
        setSelectedImages(selectedImages.filter(id => !selectedIds.includes(id)));
      } else {
        setSelectedImages(
          selectedImages.concat(selectedIds).filter((value, index, self) => self.indexOf(value) === index)
        );
      }
    } else {
      if (isAlreadySelected) {
        setSelectedImages(selectedImages.filter(id => id !== imageId));
      } else {
        setSelectedImages([...selectedImages, imageId]);
      }
    }
    setLastSelectedImage(imageId);
    setLastWasUnselected(isAlreadySelected);
  };

  const addSelectedImages = (imageIds: string[]) => {
    setSelectedImages(prev => {
      const combined = [...prev, ...imageIds];
      return combined.filter((value, index, self) => self.indexOf(value) === index);
    });
  };

  // Cache image data for selected images so they survive filter changes
  const [selectedImageCache, setSelectedImageCache] = useState<Record<string, OSImage>>({});

  const clearSelectedImages = useCallback(() => {
    setSelectedImages([]);
    setSelectedImageCache({});
  }, []);

  // Keep cache in sync: add newly available images, remove deselected ones
  useEffect(() => {
    setSelectedImageCache(prev => {
      const next = { ...prev };
      // Add any newly visible selected images
      for (const img of images) {
        if (selectedImages.includes(img.id)) {
          next[img.id] = img;
        }
      }
      // Remove deselected ones
      for (const id of Object.keys(next)) {
        if (!selectedImages.includes(id)) {
          delete next[id];
        }
      }
      return next;
    });
  }, [selectedImages, images]);

  // Stable array of selected image objects (preserves selection order)
  const selectedImageObjects = useMemo(
    () => selectedImages.map(id => selectedImageCache[id]).filter(Boolean) as OSImage[],
    [selectedImages, selectedImageCache]
  );

  return {
    isSelecting,
    setIsSelecting,
    selectedImages,
    selectedImageObjects,
    toggleSelectedImage,
    addSelectedImages,
    clearSelectedImages,
  };
}
