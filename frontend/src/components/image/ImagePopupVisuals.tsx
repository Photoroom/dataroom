import React, { useEffect, useRef } from "react";
import { OSImage, OSImageLatent, OSImageSegmentation } from "../../api/client.schemas";
import { IMAGE_SEGMENT_COLORS } from "./ImageSegmentButton";

interface ImagePopupVisualsProps {
  width: number;
  height: number;
  image: OSImage;
  // masks
  masks: OSImageLatent[];
  selectedMasks: Set<string>;
  // segments
  isLoadingSegmentation: boolean;
  segmentationData?: OSImageSegmentation;
  selectedSegments: Set<number>;
  hoveredSegments: Set<number>;
  onToggleSegment: (segment: number) => void;
  onSetHoveredSegments: (segments: Set<number>) => void;
}

export const ImagePopupVisuals: React.FC<ImagePopupVisualsProps> = ({
  width,
  height,
  image,
  // masks
  masks,
  selectedMasks,
  // segments
  segmentationData,
  selectedSegments,
  hoveredSegments,
  onToggleSegment,
  onSetHoveredSegments,
}) => {
  // Cast segments to correct type: the generated schema incorrectly defines segments as number[][],
  // but the backend actually returns number[][][] (array of 2D segment masks)
  const segments = segmentationData?.segments as unknown as number[][][];

  // -------------------- Draw segments --------------------
  const canvasRefs = useRef<Map<number, HTMLCanvasElement>>(new Map());
  const imageDataCache = useRef<Map<number, ImageData>>(new Map());

  useEffect(() => {
    if (!segmentationData || !width || !height || !segments) return;

    segments.forEach((segment, segmentIndex) => {
      const canvas = canvasRefs.current.get(segmentIndex);
      if (!canvas) return;

      const ctx = canvas.getContext("2d");
      if (!ctx) return;

      // Create ImageData for this segment
      const imageData = ctx.createImageData(canvas.width, canvas.height);
      const color = IMAGE_SEGMENT_COLORS[segmentIndex % IMAGE_SEGMENT_COLORS.length];
      const [r, g, b] = hexToRgb(color);

      // Scale segment to image size
      const scaleX = width / segment[0].length;
      const scaleY = height / segment.length;

      for (let y = 0; y < height; y++) {
        for (let x = 0; x < width; x++) {
          const segmentX = Math.floor(x / scaleX);
          const segmentY = Math.floor(y / scaleY);
          const alpha = segment[segmentY]?.[segmentX] || 0;

          const pixelIndex = (y * width + x) * 4;
          imageData.data[pixelIndex] = r;
          imageData.data[pixelIndex + 1] = g;
          imageData.data[pixelIndex + 2] = b;
          imageData.data[pixelIndex + 3] = alpha;
        }
      }

      // Cache the ImageData
      imageDataCache.current.set(segmentIndex, imageData);
      ctx.putImageData(imageData, 0, 0);
    });
  }, [segmentationData, width, height]);

  // Restore canvas contents after React updates
  useEffect(() => {
    canvasRefs.current.forEach((canvas, segmentIndex) => {
      const ctx = canvas.getContext("2d");
      const imageData = imageDataCache.current.get(segmentIndex);
      if (ctx && imageData) {
        ctx.putImageData(imageData, 0, 0);
      }
    });
  });

  // -------------------- Segment hover --------------------
  const imageRef = useRef<HTMLImageElement>(null);
  const getImageRect = useRef(() => imageRef.current?.getBoundingClientRect() || null);

  const getSegmentCoordinates = (e: React.MouseEvent) => {
    if (!segmentationData || !width || !height) return null;

    const rect = getImageRect.current();
    if (!rect) return null;

    // Check if mouse is within image bounds
    if (e.clientX < rect.left || e.clientX > rect.right || e.clientY < rect.top || e.clientY > rect.bottom) {
      return null;
    }

    // Calculate position relative to the image
    const x = (e.clientX - rect.left) / rect.width;
    const y = (e.clientY - rect.top) / rect.height;

    // Convert coordinates to segment space
    const segmentX = Math.floor(x * segments[0][0].length);
    const segmentY = Math.floor(y * segments[0].length);

    return { segmentX, segmentY };
  };

  const handleMouseMove = (e: React.MouseEvent) => {
    const coords = getSegmentCoordinates(e);
    if (!coords) {
      if (hoveredSegments.size > 0) {
        onSetHoveredSegments(new Set());
      }
      return;
    }

    // Check which segments are under the cursor
    let changed = false;
    const newHoveredSegments = new Set<number>();
    segments.forEach((segment, index) => {
      if (segment[coords.segmentY]?.[coords.segmentX] > 0) {
        newHoveredSegments.add(index);
        if (!hoveredSegments.has(index)) changed = true;
      } else if (hoveredSegments.has(index)) {
        changed = true;
      }
    });

    // Only update state if the hovered segments changed
    if (changed) {
      onSetHoveredSegments(newHoveredSegments);
    }
  };

  const handleMouseLeave = () => {
    onSetHoveredSegments(new Set());
  };

  // -------------------- Segment click --------------------
  const handleClick = (e: React.MouseEvent) => {
    const coords = getSegmentCoordinates(e);
    if (!coords) return;

    segments.forEach((segment, index) => {
      if (segment[coords.segmentY]?.[coords.segmentX] > 0) {
        onToggleSegment(index);
      }
    });
  };

  // -------------------- Render --------------------
  return (
    <div
      className="relative bg-black/8 dark:bg-white/8"
      onMouseMove={handleMouseMove}
      onMouseLeave={handleMouseLeave}
      onClick={handleClick}
      style={{
        cursor: hoveredSegments.size > 0 ? "pointer" : "default",
        width: width,
        height: height,
        backgroundSize: "contain",
        backgroundImage: `url('${image?.thumbnail}')`, // use thumbnail for faster previews
      }}
    >
      <img ref={imageRef} src={image.image} alt="" className="size-full pointer-events-none" />
      {segments?.map((_, index) => (
        <canvas
          key={index}
          ref={el => {
            if (el) {
              el.width = width;
              el.height = height;
              canvasRefs.current.set(index, el);
            }
          }}
          className="absolute top-0 left-0 max-w-full max-h-full"
          style={{
            mixBlendMode: "multiply",
            display: selectedSegments.has(index) ? "block" : "none",
            objectFit: "contain",
            opacity: hoveredSegments.has(index) ? 0.8 : 0.5,
          }}
        />
      ))}
      {masks.map((mask, index) => (
        <img
          key={index}
          src={mask.file_direct_url}
          alt=""
          className="absolute top-0 left-0 max-w-full max-h-full object-contain"
          style={{
            display: selectedMasks.has(mask.latent_type) ? "block" : "none",
            opacity: 0.5,
            width: width,
            height: height,
          }}
        />
      ))}
    </div>
  );
};

function hexToRgb(hex: string): [number, number, number] {
  const result = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex);
  if (!result) return [0, 0, 0];
  return [parseInt(result[1], 16), parseInt(result[2], 16), parseInt(result[3], 16)];
}
