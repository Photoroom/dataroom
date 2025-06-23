import React, { useEffect, useState, useCallback, useRef } from "react";
import { twMerge } from "tailwind-merge";
import { OSImage, OSImageLatent } from "../../api/client.schemas";
import { CloseButton } from "../common/CloseButton";
import { ArrowTopRightOnSquareIcon, PhotoIcon } from "@heroicons/react/24/outline";
import { ImagePopupSidebar } from "./ImagePopupSidebar";
import { ImagePopupVisuals } from "./ImagePopupVisuals";
import { useImagesSegmentationRetrieve } from "../../api/client";

interface ImagePopupProps {
  image: OSImage;
  isOpen: boolean;
  onClose: () => void;
}

export const ImagePopup: React.FC<ImagePopupProps> = ({ image, isOpen, onClose }) => {
  const containerRef = useRef<HTMLDivElement>(null);

  // -------------------- Dimensions --------------------
  const [width, setWidth] = useState(image.width ?? 1280);
  const [height, setHeight] = useState(image.height ?? 720);

  const resizeToFit = useCallback(() => {
    if (!image.width || !image.height || !containerRef.current) return;

    // Get container dimensions instead of viewport
    const containerRect = containerRef.current.getBoundingClientRect();
    const containerWidth = containerRect.width;
    const containerHeight = containerRect.height;
    
    const imageAspectRatio = image.width / image.height;
    
    let newWidth = image.width;
    let newHeight = image.height;
    
    if (newWidth > containerWidth || newHeight > containerHeight) {
      if (containerWidth / containerHeight < imageAspectRatio) {
        // landscape
        newWidth = containerWidth;
        newHeight = newWidth / imageAspectRatio;
      } else {
        // portrait
        newHeight = containerHeight;
        newWidth = newHeight * imageAspectRatio;
      }
    }
    
    setWidth(Math.round(newWidth));
    setHeight(Math.round(newHeight));
  }, [image.width, image.height]);

  useEffect(() => {
    // initial resize
    resizeToFit();
    
    window.addEventListener('resize', resizeToFit);
    
    return () => {
      window.removeEventListener('resize', resizeToFit);
    };
  }, [resizeToFit]);

  useEffect(() => {
    resizeToFit();
  }, [isOpen]);

  // -------------------- Masks --------------------
  const [selectedMasks, setSelectedMasks] = useState<Set<string>>(new Set());
  const [masks, setMasks] = useState<OSImageLatent[]>(image.latents?.filter((latent) => latent.is_mask === true) ?? []);

  const handleSelectNoMasks = () => {
    setSelectedMasks(new Set());
  };

  const handleSelectAllMasks = () => {
    setSelectedMasks(new Set(masks.map((mask) => mask.latent_type)));
  };

  const handleToggleMask = (mask: string) => {
    setSelectedMasks(prev => {
      const next = new Set(prev);
      if (next.has(mask)) {
        next.delete(mask);
      } else {
        next.add(mask);
      }
      return next;
    });
  };
  
  // -------------------- Segmentation --------------------
  const [selectedSegments, setSelectedSegments] = useState<Set<number>>(new Set());
  const [hoveredSegments, setHoveredSegments] = useState<Set<number>>(new Set());
  const { data: segmentationData, isLoading: isLoadingSegmentation, error: segmentationError } = useImagesSegmentationRetrieve(image.id);

  const handleSelectNoSegments = () => {
    setSelectedSegments(new Set());
  };

  const handleSelectAllSegments = () => {
    if (!segmentationData) return;
    setSelectedSegments(new Set(segmentationData.captions.map((_, i) => i)));
  };

  const handleToggleSegment = (index: number) => {
    setSelectedSegments(prev => {
      const next = new Set(prev);
      if (next.has(index)) {
        next.delete(index);
      } else {
        next.add(index);
      }
      return next;
    });
  };

  // -------------------- Render --------------------
  return (
    <div
      className={twMerge(
        "fixed z-40 inset-0 size-full bg-light dark:bg-dark",
        isOpen ? "fixed" : "hidden"
      )}
    >
      <CloseButton onClick={onClose} className="opacity-70" />
      <a
        type="button"
        href={image.image}
        target="_blank"
        title="Image file"
        className={twMerge(
          "absolute top-0 right-12 z-20 cursor-pointer size-12",
          "flex items-center justify-center",
          "text-black dark:text-white",
          "opacity-70 hover:opacity-100 transition-opacity",
        )}
      >
        <ArrowTopRightOnSquareIcon className="size-5 mx-auto" />
      </a>

      <div className="h-full grid grid-rows-[160px_1fr] md:grid-rows-1 md:grid-cols-[300px_1fr]">
        <div className="min-h-[60px] h-auto md:h-full overflow-y-auto">
          <ImagePopupSidebar
            image={image}
            masks={masks}
            selectedMasks={selectedMasks}
            onSelectNoMasks={handleSelectNoMasks}
            onSelectAllMasks={handleSelectAllMasks}
            onToggleMask={handleToggleMask}
            isLoadingSegmentation={isLoadingSegmentation}
            segmentationError={segmentationError}
            segmentationData={segmentationData}
            selectedSegments={selectedSegments}
            hoveredSegments={hoveredSegments}
            onSelectNoSegments={handleSelectNoSegments}
            onSelectAllSegments={handleSelectAllSegments}
            onToggleSegment={handleToggleSegment}
          />
        </div>
        <div className="relative h-full w-full">
          <div className="pt-3 px-4 md:mr-22">
            <PhotoIcon className="size-4 shrink-0 inline-block leading-none mr-1.5" />
            <span className="font-bold break-all">{image.id}</span>
          </div>
          <div ref={containerRef} className="absolute inset-4 top-[50px]">
            <ImagePopupVisuals
              image={image}
              width={width}
              height={height}
              masks={masks}
              selectedMasks={selectedMasks}
              isLoadingSegmentation={isLoadingSegmentation}
              segmentationData={segmentationData}
              selectedSegments={selectedSegments}
              hoveredSegments={hoveredSegments}
              onToggleSegment={handleToggleSegment}
              onSetHoveredSegments={setHoveredSegments}
            />
          </div>
        </div>
      </div>
    </div>
  );
};
