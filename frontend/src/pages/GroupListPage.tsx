import React, { useCallback, useEffect, useRef, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { twMerge } from "tailwind-merge";
import { MainContainer } from "../layouts/MainContainer";
import { GroupsFilterSidebar } from "../layouts/groups/GroupsFilterSidebar";
import { useGroupsList } from "../api/client";
import { useImageListData } from "../context/ImageListDataContext";
import { useGroupDrawer } from "../context/GroupDrawerContext";
import { useGroupSelection } from "../context/GroupSelectionContext";
import { useDragSelect } from "../context/useDragSelect";
import { toast } from "react-hot-toast";
import { LoaderSkeleton } from "../components/common/LoaderSkeleton";
import { GroupCard } from "../components/group/GroupCard";

const PAGE_SIZE_OPTIONS = [24, 48, 96, 200];
const DEFAULT_PAGE_SIZE = 24;

/** Pull the `cursor` query value out of a DRF next/previous URL. */
function cursorOf(url?: string | null): string | undefined {
  if (!url) return undefined;
  try {
    return new URL(url, window.location.origin).searchParams.get("cursor") ?? undefined;
  } catch {
    return undefined;
  }
}

export const GroupListPage: React.FC = function () {
  const [searchParams] = useSearchParams();
  const typeFilter = searchParams.get("type") ?? "";
  const types = typeFilter ? typeFilter.split(",").filter(Boolean) : undefined;
  const namePrefix = searchParams.get("name__prefix") || undefined;
  const coverRole = searchParams.get("cover_role") || undefined;
  // CSV, any-of: groups that are members of at least one listed dataset
  const datasetFilter = searchParams.get("dataset") ?? "";
  const datasets = datasetFilter ? datasetFilter.split(",").filter(Boolean) : undefined;

  const [cursor, setCursor] = useState<string | undefined>(undefined);
  const [pageSize, setPageSize] = useState<number>(() => {
    const saved = Number(localStorage.getItem("groupsPageSize"));
    return PAGE_SIZE_OPTIONS.includes(saved) ? saved : DEFAULT_PAGE_SIZE;
  });

  // Reset to the first page whenever the filters or page size change.
  useEffect(() => {
    setCursor(undefined);
  }, [typeFilter, namePrefix, coverRole, datasetFilter, pageSize]);

  const {
    data: groups,
    isLoading,
    isError,
  } = useGroupsList({
    type: types,
    name__prefix: namePrefix,
    cover_role: coverRole,
    dataset: datasets,
    page_size: pageSize,
    cursor,
  });
  const { gridColumns } = useImageListData();
  const { isDrawerOpen } = useGroupDrawer();
  const { isSelecting, selectionType, registerGroups, addSelectedGroups } = useGroupSelection();
  const gridStyle = { gridTemplateColumns: `repeat(${gridColumns}, minmax(0, 1fr))` };

  const mainDivRef = useRef<HTMLDivElement>(null);
  const results = groups?.results ?? [];

  // Marquee (drag) selection maps hit tile ids back to the groups on this page.
  const onDragSelect = useCallback(
    (ids: string[]) => {
      const byId = new Map(results.map(g => [g.id, g]));
      let picked = ids.map(id => byId.get(id)).filter((g): g is (typeof results)[number] => Boolean(g));
      // Keep the selection single-type: lock to the current type, else the first hit.
      const lockType = selectionType ?? picked[0]?.type ?? null;
      if (lockType) picked = picked.filter(g => g.type === lockType);
      if (picked.length > 0) addSelectedGroups(picked);
    },
    [results, addSelectedGroups, selectionType]
  );
  const { selectionRect, onMouseDown, onClickCapture } = useDragSelect({
    containerRef: mainDivRef,
    enabled: isSelecting,
    attribute: "data-group-id",
    onSelect: onDragSelect,
  });

  useEffect(() => {
    if (isError) {
      toast.error("Error loading groups");
    }
  }, [isError]);

  // Keep the selection provider's ordered list in sync for shift-range selection.
  useEffect(() => {
    registerGroups(results);
  }, [results, registerGroups]);
  const hasPrev = Boolean(groups?.previous);
  const hasNext = Boolean(groups?.next);

  return (
    <>
      <GroupsFilterSidebar />
      <MainContainer ref={mainDivRef} isDrawerOpen={isDrawerOpen} isSidebarOpen>
        {selectionRect && (
          <div
            style={{
              position: "absolute",
              left: selectionRect.left,
              top: selectionRect.top,
              width: selectionRect.width,
              height: selectionRect.height,
              pointerEvents: "none",
              zIndex: 50,
            }}
            className="border border-brand-400 bg-brand-400/10"
          />
        )}
        <div className="flex flex-col">
          {isLoading && (
            <div className="grid gap-2 p-2 sm:gap-4 sm:p-4" style={gridStyle}>
              {Array.from({ length: 24 }).map((_, i) => (
                <LoaderSkeleton key={i} className="w-full aspect-square rounded-lg" />
              ))}
            </div>
          )}
          {!isLoading && results.length === 0 && (
            <p className="text-sm opacity-50 p-4">
              {typeFilter ? `No groups matching type filter.` : "No groups yet."}
            </p>
          )}
          {!isLoading && results.length > 0 && (
            <div
              onMouseDown={onMouseDown}
              onClickCapture={onClickCapture}
              style={gridStyle}
              className={twMerge("grid gap-2 p-2 sm:gap-4 sm:p-4", isSelecting ? "select-none" : "")}
            >
              {results.map(group => (
                <GroupCard key={group.id} group={group} />
              ))}
            </div>
          )}
          {!isLoading && (hasPrev || hasNext) && (
            <div className="flex flex-row items-center justify-center gap-3 my-10 min-h-12">
              <button
                type="button"
                disabled={!hasPrev}
                onClick={() => setCursor(cursorOf(groups?.previous))}
                className="px-3 py-1.5 text-sm rounded-lg border border-black/10 dark:border-white/10 enabled:hover:bg-black/5 dark:enabled:hover:bg-white/5 disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer"
              >
                &larr; Prev
              </button>
              <button
                type="button"
                disabled={!hasNext}
                onClick={() => setCursor(cursorOf(groups?.next))}
                className="px-3 py-1.5 text-sm rounded-lg border border-black/10 dark:border-white/10 enabled:hover:bg-black/5 dark:enabled:hover:bg-white/5 disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer"
              >
                Next &rarr;
              </button>
              <select
                aria-label="Groups per page"
                value={pageSize}
                onChange={e => {
                  const next = Number(e.target.value);
                  setPageSize(next);
                  localStorage.setItem("groupsPageSize", String(next));
                }}
                className="ml-3 px-2 py-1.5 text-sm rounded-lg border border-black/10 dark:border-white/10 bg-transparent dark:bg-dark-100 opacity-60 hover:opacity-100 cursor-pointer"
              >
                {PAGE_SIZE_OPTIONS.map(n => (
                  <option key={n} value={n}>
                    {n} / page
                  </option>
                ))}
              </select>
            </div>
          )}
        </div>
      </MainContainer>
    </>
  );
};
