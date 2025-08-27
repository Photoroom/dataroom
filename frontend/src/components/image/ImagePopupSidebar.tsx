import React from "react";
import { OSImageLatent, OSImageSegmentation } from "../../api/client.schemas";
import { LoaderSkeleton } from "../common/LoaderSkeleton";
import { ImageSegmentButton, IMAGE_SEGMENT_COLORS } from "./ImageSegmentButton";

export type SegmentationErrorLike = {
  response?: {
    data?: {
      error?: string;
    };
  };
  message?: string;
};

interface ImagePopupSidebarProps {
  // masks
  masks: OSImageLatent[];
  selectedMasks: Set<string>;
  onSelectNoMasks: () => void;
  onSelectAllMasks: () => void;
  onToggleMask: (mask: string) => void;
  // segments
  isLoadingSegmentation: boolean;
  segmentationError?: SegmentationErrorLike | null;
  segmentationData?: OSImageSegmentation;
  selectedSegments: Set<number>;
  hoveredSegments: Set<number>;
  onSelectNoSegments: () => void;
  onSelectAllSegments: () => void;
  onToggleSegment: (segment: number) => void;
}

export const ImagePopupSidebar: React.FC<ImagePopupSidebarProps> = ({
  // masks
  masks,
  selectedMasks,
  onSelectNoMasks,
  onSelectAllMasks,
  onToggleMask,
  // segments
  isLoadingSegmentation,
  segmentationError,
  segmentationData,
  selectedSegments,
  hoveredSegments,
  onSelectNoSegments,
  onSelectAllSegments,
  onToggleSegment,
}) => {
  // -------------------- Render --------------------
  return (
    <div className="w-full flex flex-col items-start justify-center gap-2 p-2 pb-8">
      <h4 className="text-xs px-2 pt-4 uppercase text-sm tracking-wide opacity-70">Masks</h4>
      {masks.length === 0 && (
        <div className="w-full flex flex-col items-stretch gap-1 shrink-0 px-2">
          <p className="text-xs opacity-50">No masks found</p>
        </div>
      )}
      {masks.length > 0 && (
        <div className="w-full flex flex-col items-stretch gap-1 shrink-0">
          <ImageSegmentButton
            caption="All masks"
            selected={selectedMasks.size === masks.length}
            onClick={() => {
              if (selectedMasks.size === masks.length) {
                onSelectNoMasks();
              } else {
                onSelectAllMasks();
              }
            }}
            count={masks.length}
          />
          {masks.map((mask, index) => (
            <ImageSegmentButton
              key={index}
              caption={mask.latent_type}
              selected={selectedMasks.has(mask.latent_type)}
              onClick={() => onToggleMask(mask.latent_type)}
            />
          ))}
        </div>
      )}

      <h4 className="text-xs px-2 pt-4 uppercase text-sm tracking-wide opacity-70">Segments</h4>
      {isLoadingSegmentation && (
        <div className="w-full flex flex-col items-stretch gap-1 shrink-0 px-2">
          <LoaderSkeleton className="h-8" />
          <LoaderSkeleton className="h-8" />
          <LoaderSkeleton className="h-8" />
        </div>
      )}
      {!isLoadingSegmentation && !!segmentationError && (
        <div className="w-full flex flex-col items-stretch gap-1 shrink-0 px-2">
          <p className="text-xs opacity-50">{segmentationError?.response?.data?.error || segmentationError?.message}</p>
        </div>
      )}
      {!isLoadingSegmentation && segmentationData?.captions.length === 0 && (
        <div className="w-full flex flex-col items-stretch gap-1 shrink-0 px-2">
          <p className="text-xs opacity-50">No segments found</p>
        </div>
      )}
      {!isLoadingSegmentation && segmentationData && segmentationData?.captions.length > 0 && (
        <div className="w-full flex flex-col items-stretch gap-1 shrink-0">
          <ImageSegmentButton
            caption="All segments"
            selected={selectedSegments.size === segmentationData?.captions.length}
            onClick={() => {
              if (selectedSegments.size === segmentationData?.captions.length) {
                onSelectNoSegments();
              } else {
                onSelectAllSegments();
              }
            }}
            count={segmentationData?.segments.length}
          />
          {segmentationData?.captions.map((caption, index) => (
            <ImageSegmentButton
              key={index}
              caption={caption}
              color={IMAGE_SEGMENT_COLORS[index % IMAGE_SEGMENT_COLORS.length]}
              selected={selectedSegments.has(index)}
              highlighted={hoveredSegments.has(index)}
              onClick={() => onToggleSegment(index)}
            />
          ))}
        </div>
      )}
    </div>
  );
};
