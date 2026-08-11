import React, { useEffect, useMemo, useState } from "react";
import { useSearchParams } from "react-router-dom";
import { MainContainer } from "../layouts/MainContainer";
import { DatasetsFilterSidebar } from "../layouts/datasets/DatasetsFilterSidebar";
import { useDatasetsList } from "../api/client";
import { useImageListData } from "../context/ImageListDataContext";
import { useDatasetDrawer } from "../context/DatasetDrawerContext";
import { toast } from "react-hot-toast";
import { Card } from "../components/common/Card";
import { LoaderSkeleton } from "../components/common/LoaderSkeleton";
import { Dataset } from "../api/client.schemas";
import { DatasetCard } from "../components/dataset/DatasetCard";

const PAGE_SIZE_OPTIONS = [24, 48, 96, 200];
const DEFAULT_PAGE_SIZE = 48;

/** Pull the `cursor` query value out of a DRF next/previous URL. */
function cursorOf(url?: string | null): string | undefined {
  if (!url) return undefined;
  try {
    return new URL(url, window.location.origin).searchParams.get("cursor") ?? undefined;
  } catch {
    return undefined;
  }
}

export const DatasetListPage: React.FC = function () {
  const [searchParams] = useSearchParams();
  const showAllVersions = searchParams.get("all_versions") === "1";
  const isFrozenParam = searchParams.get("is_frozen");
  const search = searchParams.get("search") || undefined;
  const type = searchParams.get("type") || undefined;

  const [cursor, setCursor] = useState<string | undefined>(undefined);
  const [pageSize, setPageSize] = useState<number>(() => {
    const saved = Number(localStorage.getItem("datasetsPageSize"));
    return PAGE_SIZE_OPTIONS.includes(saved) ? saved : DEFAULT_PAGE_SIZE;
  });

  // Back to the first page whenever the filters or page size change.
  useEffect(() => {
    setCursor(undefined);
  }, [search, type, isFrozenParam, showAllVersions, pageSize]);

  const {
    data: datasets,
    isLoading: isLoadingDatasets,
    isError: isErrorDatasets,
  } = useDatasetsList({
    search,
    type,
    is_frozen: isFrozenParam === null ? undefined : isFrozenParam === "true",
    page_size: pageSize,
    cursor,
  });
  const { gridColumns } = useImageListData();
  const { isDrawerOpen } = useDatasetDrawer();
  // Dataset cards read denser than image tiles at the same density, so render
  // them a step bigger than the shared grid slider (still tracks it).
  const datasetColumns = Math.max(2, gridColumns - 2);
  const gridStyle = { gridTemplateColumns: `repeat(${datasetColumns}, minmax(0, 1fr))` };

  useEffect(() => {
    if (isErrorDatasets) {
      toast.error("Error loading datasets");
    }
  }, [isErrorDatasets]);

  // Default view collapses each slug to its latest version; the "show all
  // versions" filter lists every version as its own card. The collapse is
  // per page — ordering is (slug, -version), so versions sit adjacent and
  // only a slug straddling a page boundary can appear on both pages.
  const visibleDatasets = useMemo(() => {
    const results = datasets?.results ?? [];
    if (showAllVersions) return results;
    const latest: Record<string, Dataset> = {};
    for (const dataset of results) {
      if (dataset.version > (latest[dataset.slug]?.version || 0)) {
        latest[dataset.slug] = dataset;
      }
    }
    return Object.values(latest);
  }, [datasets, showAllVersions]);

  const hasPrev = Boolean(datasets?.previous);
  const hasNext = Boolean(datasets?.next);

  return (
    <>
      <DatasetsFilterSidebar />
      <MainContainer isDrawerOpen={isDrawerOpen} isSidebarOpen>
        <div className="w-full">
          {isLoadingDatasets && (
            <div className="grid gap-4 p-3 sm:gap-6 sm:p-6" style={gridStyle}>
              {Array.from({ length: 12 }).map((_, i) => (
                <Card key={i} className="flex-col overflow-hidden">
                  <LoaderSkeleton className="w-full aspect-square" />
                  <div className="flex flex-col gap-2 p-2">
                    <LoaderSkeleton className="h-4 w-3/4" />
                  </div>
                </Card>
              ))}
            </div>
          )}
          {!isLoadingDatasets && visibleDatasets.length === 0 && (
            <p className="text-sm opacity-50 p-4">
              {datasets?.results?.length === 0 && !searchParams.toString() ? (
                <>
                  No datasets yet. Use <strong>Create dataset</strong> to add one.
                </>
              ) : (
                "No datasets match the filters."
              )}
            </p>
          )}
          {!isLoadingDatasets && visibleDatasets.length > 0 && (
            <div className="grid gap-4 p-3 sm:gap-6 sm:p-6" style={gridStyle}>
              {visibleDatasets.map(dataset => (
                <DatasetCard key={dataset.slug_version} dataset={dataset} />
              ))}
            </div>
          )}
          {!isLoadingDatasets && (hasPrev || hasNext) && (
            <div className="flex flex-row items-center justify-center gap-3 my-10 min-h-12">
              <button
                type="button"
                disabled={!hasPrev}
                onClick={() => setCursor(cursorOf(datasets?.previous))}
                className="px-3 py-1.5 text-sm rounded-lg border border-black/10 dark:border-white/10 enabled:hover:bg-black/5 dark:enabled:hover:bg-white/5 disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer"
              >
                &larr; Prev
              </button>
              <button
                type="button"
                disabled={!hasNext}
                onClick={() => setCursor(cursorOf(datasets?.next))}
                className="px-3 py-1.5 text-sm rounded-lg border border-black/10 dark:border-white/10 enabled:hover:bg-black/5 dark:enabled:hover:bg-white/5 disabled:opacity-30 disabled:cursor-not-allowed cursor-pointer"
              >
                Next &rarr;
              </button>
              <select
                aria-label="Datasets per page"
                value={pageSize}
                onChange={e => {
                  const next = Number(e.target.value);
                  setPageSize(next);
                  localStorage.setItem("datasetsPageSize", String(next));
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
