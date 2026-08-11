import React, { useEffect, useState } from "react";
import ReactDOM from "react-dom";
import { twMerge } from "tailwind-merge";
import { OSImage } from "../../api/client.schemas";
import { ImagePopup } from "./ImagePopup";

interface ZoomableImageProps {
  image?: OSImage;
  className?: string;
  style?: React.CSSProperties;
  children: React.ReactNode;
  /** Pass through to ImagePopup. Set false for a plain zoom without the
      masks/segmentation sidebar (e.g. group member thumbnails). */
  showAnalysis?: boolean;
  /** Custom sidebar content for the enlarged view (replaces analysis UI). */
  sidebar?: React.ReactNode;
  /** Controlled open state. When provided, the parent owns open/close (e.g. so
      clicking a whole member row — not just the thumbnail — opens the zoom). */
  open?: boolean;
  onOpenChange?: (open: boolean) => void;
}

/**
 * Wraps arbitrary image content and opens the full-screen ImagePopup lightbox
 * on click — the same zoom behavior used in the images views. Layout-agnostic:
 * the caller controls sizing/cropping of `children`.
 */
export const ZoomableImage: React.FC<ZoomableImageProps> = ({
  image,
  className,
  style,
  children,
  showAnalysis = true,
  sidebar,
  open,
  onOpenChange,
}) => {
  const [internalOpen, setInternalOpen] = useState(false);
  const isControlled = open !== undefined;
  const isOpen = isControlled ? open : internalOpen;
  const setOpen = (next: boolean) => {
    if (!isControlled) setInternalOpen(next);
    onOpenChange?.(next);
  };
  const close = () => setOpen(false);

  useEffect(() => {
    const onEsc = (e: KeyboardEvent) => {
      if (e.key === "Escape" && isOpen) close();
    };
    window.addEventListener("keydown", onEsc);
    return () => window.removeEventListener("keydown", onEsc);
  }, [isOpen]);

  if (!image) {
    return (
      <div className={className} style={style}>
        {children}
      </div>
    );
  }

  return (
    <>
      <button
        type="button"
        onClick={() => setOpen(true)}
        title="Click to zoom"
        className={twMerge("cursor-zoom-in", className)}
        style={style}
      >
        {children}
      </button>
      {/* Mount the popup only while open — otherwise every ZoomableImage on a
          page (e.g. all members on a group detail page) would mount a hidden
          ImagePopup that eagerly fetches segmentation for its image. */}
      {isOpen &&
        ReactDOM.createPortal(
          <ImagePopup image={image} isOpen={isOpen} onClose={close} showAnalysis={showAnalysis} sidebar={sidebar} />,
          document.body
        )}
    </>
  );
};
