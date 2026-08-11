import React, { useCallback, useEffect, useRef, useState } from "react";

interface Rect {
  left: number;
  top: number;
  width: number;
  height: number;
}

// Marquee select over a scroll container. Coords are content-space (+ scroll
// offset) so scrolling mid-drag doesn't desync the rect. Reports ids of tiles
// matching `[attribute]` via onSelect.
export function useDragSelect({
  containerRef,
  enabled,
  attribute,
  onSelect,
}: {
  containerRef: React.RefObject<HTMLDivElement | null>;
  enabled: boolean;
  attribute: string; // e.g. "data-image-id"
  onSelect: (ids: string[]) => void;
}) {
  const dragRef = useRef<{ active: boolean; startX: number; startY: number; didDrag: boolean } | null>(null);
  const wasDragRef = useRef(false);
  const [selectionRect, setSelectionRect] = useState<Rect | null>(null);

  // 5px threshold = drag vs click; smaller movements fall through to the tile.
  const onMouseDown = useCallback(
    (e: React.MouseEvent) => {
      if (!enabled || e.button !== 0) return;
      const div = containerRef.current;
      if (!div) return;
      const r = div.getBoundingClientRect();
      dragRef.current = {
        active: true,
        startX: e.clientX - r.left + div.scrollLeft,
        startY: e.clientY - r.top + div.scrollTop,
        didDrag: false,
      };
    },
    [enabled, containerRef]
  );

  // swallow the click that fires right after a drag-release
  const onClickCapture = useCallback((e: React.MouseEvent) => {
    if (wasDragRef.current) {
      e.stopPropagation();
      e.preventDefault();
      wasDragRef.current = false;
    }
  }, []);

  useEffect(() => {
    const DRAG_THRESHOLD = 5;

    const handleMouseMove = (e: MouseEvent) => {
      if (!dragRef.current?.active) return;
      const div = containerRef.current;
      if (!div) return;
      const divRect = div.getBoundingClientRect();
      const { startX, startY } = dragRef.current;
      const cx = e.clientX - divRect.left + div.scrollLeft;
      const cy = e.clientY - divRect.top + div.scrollTop;
      const dx = cx - startX;
      const dy = cy - startY;
      if (Math.abs(dx) > DRAG_THRESHOLD || Math.abs(dy) > DRAG_THRESHOLD) {
        dragRef.current.didDrag = true;
        setSelectionRect({
          left: Math.min(startX, cx),
          top: Math.min(startY, cy),
          width: Math.abs(dx),
          height: Math.abs(dy),
        });
      }
    };

    const handleMouseUp = (e: MouseEvent) => {
      if (!dragRef.current?.active) return;
      const { startX, startY, didDrag } = dragRef.current;
      dragRef.current = null;
      setSelectionRect(null);
      if (!didDrag) return; // regular click — let the tile's onClick handle it
      wasDragRef.current = true;

      const div = containerRef.current;
      if (!div) return;
      const divRect = div.getBoundingClientRect();
      const endX = e.clientX - divRect.left + div.scrollLeft;
      const endY = e.clientY - divRect.top + div.scrollTop;
      const selLeft = Math.min(startX, endX);
      const selTop = Math.min(startY, endY);
      const selRight = Math.max(startX, endX);
      const selBottom = Math.max(startY, endY);

      const ids: string[] = [];
      document.querySelectorAll<HTMLElement>(`[${attribute}]`).forEach(tile => {
        const tr = tile.getBoundingClientRect();
        const tLeft = tr.left - divRect.left + div.scrollLeft;
        const tTop = tr.top - divRect.top + div.scrollTop;
        const tRight = tr.right - divRect.left + div.scrollLeft;
        const tBottom = tr.bottom - divRect.top + div.scrollTop;
        if (tRight >= selLeft && tLeft <= selRight && tBottom >= selTop && tTop <= selBottom) {
          const id = tile.getAttribute(attribute);
          if (id) ids.push(id);
        }
      });
      if (ids.length > 0) onSelect(ids);
    };

    document.addEventListener("mousemove", handleMouseMove);
    document.addEventListener("mouseup", handleMouseUp);
    return () => {
      document.removeEventListener("mousemove", handleMouseMove);
      document.removeEventListener("mouseup", handleMouseUp);
    };
  }, [attribute, onSelect, containerRef]);

  return { selectionRect, onMouseDown, onClickCapture };
}
