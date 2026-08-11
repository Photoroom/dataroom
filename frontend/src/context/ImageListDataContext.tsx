import React, { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState } from "react";
import { useLocation, useSearchParams } from "react-router-dom";
import { useImagesList, useImagesCountRetrieve, useQueriesRetrieve } from "../api/client";
import { URLS } from "../urls";
import { OSImage, PaginatedOSImage } from "../api/client.schemas";
import { axiosInstance } from "../api/axios";
import toast from "react-hot-toast";
import {
  genChipId,
  createEmptyLane,
  lanesToApiParams,
  lanesToAllFilterParamKeys,
  parseLanesFromUrl,
  isAdvancedFilter,
} from "./filterUtils";
import { useImageSelection } from "./useImageSelection";
import { useSimilaritySearch } from "./useSimilaritySearch";
import { extractApiError } from "../api/errors";

export enum ImageListMode {
  BROWSE = "browse",
  SIMILAR = "similar",
}

export interface FilterChip {
  id: string;
  field: string; // "source", "tag", "width", "attr:color", etc.
  operator: string; // "eq", "ne", "gt", "gte", "lt", "lte", "match", "prefix"
  value: string;
}

export interface FilterLane {
  id: string;
  chips: FilterChip[];
  negated: boolean;
}

interface ImageListDataContextType {
  // image list
  images: OSImage[];
  isLoadingImages: boolean;
  isLoadingImagesError: boolean;
  hasNextPage: boolean;
  loadNextPage: () => void;
  isLoadingNextPage: boolean;
  isLoadingNextPageError: boolean;
  // mode
  mode: ImageListMode;
  setModeBrowse: () => void;
  // similarity search
  setModeSimilarImage: (imageId: string) => void;
  similarImage: OSImage | null;
  setModeSimilarText: (text: string) => void;
  similarText: string | null;
  setModeSimilarFile: (file: File) => void;
  similarFile: File | null;
  setModeSimilarVector: (vector: string) => void;
  similarVector: string | null;
  // selecting
  isSelecting: boolean;
  setIsSelecting: (isSelecting: boolean) => void;
  selectedImages: string[];
  selectedImageObjects: OSImage[];
  toggleSelectedImage: (imageId: string, isMultiSelect: boolean) => void;
  addSelectedImages: (imageIds: string[]) => void;
  clearSelectedImages: () => void;
  // grid
  gridColumns: number;
  setGridColumns: (columns: number) => void;
  // filters
  chips: FilterChip[];
  addChip: (chip: Omit<FilterChip, "id">) => void;
  removeChip: (id: string) => void;
  removeChipDraft: (id: string) => void;
  clearChips: () => void;
  // lanes
  lanes: FilterLane[];
  activeLaneId: string;
  setActiveLane: (id: string) => void;
  addLane: () => void;
  removeLane: (id: string) => void;
  toggleLaneNegated: (id: string) => void;
  clearAllLanes: () => void;
  isAdvancedFilter: boolean;
  // commit
  commitFilters: () => void;
  committedFilterParams: Record<string, string>;
  // saved query the current filters are bound to (tracked in ?query=<slug>, for overwrite-on-save)
  activeQuerySlug: string | null;
  // collapsed = compact pill (filters live in committed lanes for fetching, but hidden from the bar
  // and URL which shows only ?query=<slug>); exploded = filters surfaced as editable chips + params.
  queryCollapsed: boolean;
  bindQuery: (slug: string) => void;
  clearActiveQuery: () => void;
  collapseToQuery: (slug: string, filters: Record<string, unknown>) => void;
  explodeQuery: () => void;
  collapseQuery: () => void;
  expandQueryToChips: (slug: string, filters: Record<string, unknown>) => void;
  // count
  totalCount: number | null;
  // refetch
  refetchImages: () => void;
}

const ImageListDataContext = createContext<ImageListDataContextType | undefined>(undefined);

// -------------------- Constants --------------------
const LIST_INCLUDE_FIELDS = "thumbnail,image";
const PAGE_SIZE = 100;

// -------------------- Data provider --------------------
export function ImageListDataProvider({ children }: { children: React.ReactNode }) {
  const [searchParams, setSearchParams] = useSearchParams();

  // -------------------- Get initial URL state --------------------
  const initialSimilarImageId = searchParams.get("similar") || null;
  const initialSimilarText = searchParams.get("similarText") || null;

  // -------------------- Mode state --------------------
  const [mode, setMode] = useState<ImageListMode>(() => {
    if (searchParams.get("similar") || searchParams.get("similarText")) {
      return ImageListMode.SIMILAR;
    }
    return ImageListMode.BROWSE;
  });

  // -------------------- Image list state --------------------
  const [images, setImages] = useState<OSImage[]>([]);
  const [imagesNextUrl, setImagesNextUrl] = useState<string | null>(null);
  const [isLoadingNextPage, setIsLoadingNextPage] = useState(false);
  const [isLoadingNextPageError, setIsLoadingNextPageError] = useState(false);

  // -------------------- Similarity search (extracted hook) --------------------
  const similarity = useSimilaritySearch({
    mode,
    setMode,
    onImagesLoaded: (imgs, nextUrl) => {
      setImages(imgs);
      setImagesNextUrl(nextUrl);
    },
    initialSimilarImageId,
    initialSimilarText,
  });

  // -------------------- Selection (extracted hook) --------------------
  const selection = useImageSelection(images);

  // -------------------- Grid size --------------------
  // Clamp the zoom so tiles can't blow up to absurd sizes.
  const MIN_GRID_COLUMNS = 3;
  const MAX_GRID_COLUMNS = 12;
  const clampCols = (n: number) =>
    Math.min(MAX_GRID_COLUMNS, Math.max(MIN_GRID_COLUMNS, Number.isFinite(n) ? n : MIN_GRID_COLUMNS));

  const [gridColumns, setGridColumns] = useState<number>(() => {
    const saved = localStorage.getItem("gridColumns");
    if (saved) return clampCols(Number(saved));
    return window.innerWidth < 640 ? 3 : 6;
  });

  const handleSetGridColumns = useCallback((cols: number) => {
    const next = clampCols(cols);
    setGridColumns(next);
    localStorage.setItem("gridColumns", String(next));
  }, []);

  // -------------------- Filters (lane model) --------------------
  // `lanes` is the live/draft state (edited during multi-select without triggering queries).
  // `committedLanes` is what the browse query and URL actually use.
  // Direct user actions (remove chip, clear, etc.) commit immediately.
  // addChip (used by multi-select toggle) only updates draft — committed on explicit apply.
  // Parse the URL once on mount; subsequent URL writes are driven by state, not re-parsed here.
  const initialLanes = useMemo(() => parseLanesFromUrl(searchParams), []);
  const [lanes, setLanes] = useState<FilterLane[]>(() => initialLanes);
  const [committedLanes, setCommittedLanes] = useState<FilterLane[]>(() => initialLanes);
  const [activeLaneId, setActiveLaneId] = useState<string>(() => initialLanes[0]?.id ?? createEmptyLane().id);

  // Derived: active lane's chips for backward compat
  const activeLane = useMemo(() => lanes.find(l => l.id === activeLaneId) ?? lanes[0], [lanes, activeLaneId]);
  const chips = activeLane?.chips ?? [];
  const advancedFilter = useMemo(() => isAdvancedFilter(lanes), [lanes]);

  // Browse query + URL use committed params; facets use live params via chips
  const committedFilterParams = useMemo(() => lanesToApiParams(committedLanes), [committedLanes]);

  // Binding marker for the saved query the filters came from, so Save can overwrite it. Not a
  // server-side filter (the image list always filters by the chips). Kept in state so the
  // URL-sync effect is the sole writer of ?query=, mirrored there for shareable URLs.
  const [activeQuerySlug, setActiveQuerySlug] = useState<string | null>(() => searchParams.get("query"));

  // Collapsed = compact pill: the query's filters live in committed lanes (so the list fetches),
  // but they're hidden from the bar and the URL shows only ?query=<slug>. Start collapsed when the
  // URL has ?query= but no individual filter params (i.e. a shared collapsed link).
  const [queryCollapsed, setQueryCollapsed] = useState<boolean>(
    () => !!searchParams.get("query") && !initialLanes.some(l => l.chips.length > 0)
  );

  // Turn a saved query's stored filters into editable lanes.
  const filtersToLanes = useCallback((filters: Record<string, unknown>) => {
    const sp = new URLSearchParams();
    for (const [key, value] of Object.entries(filters)) {
      if (value === null || value === undefined) continue;
      if (Array.isArray(value)) sp.set(key, value.join(","));
      else if (typeof value === "object") sp.set(key, JSON.stringify(value));
      else sp.set(key, String(value));
    }
    return parseLanesFromUrl(sp);
  }, []);

  const loadLanes = useCallback((newLanes: FilterLane[]) => {
    setLanes(newLanes);
    setCommittedLanes(newLanes);
    setActiveLaneId(newLanes[0]?.id ?? createEmptyLane().id);
  }, []);

  // Bind the current filters to a saved query (e.g. after saving) without touching the chips.
  const bindQuery = useCallback((slug: string) => setActiveQuerySlug(slug), []);

  // Detach from the bound query and clear its filters (the ✕ on the collapsed pill).
  const clearActiveQuery = useCallback(() => {
    setActiveQuerySlug(null);
    setQueryCollapsed(false);
    loadLanes([createEmptyLane()]);
  }, [loadLanes]);

  // Select a saved query: load its filters into committed lanes (so the list fetches) and bind to
  // it, but stay collapsed so the bar shows only a pill and the URL only ?query=<slug>.
  const collapseToQuery = useCallback(
    (slug: string, filters: Record<string, unknown>) => {
      setActiveQuerySlug(slug);
      loadLanes(filtersToLanes(filters));
      setQueryCollapsed(true);
    },
    [filtersToLanes, loadLanes]
  );

  // Explode the collapsed query into editable chips: lanes are already loaded, so surfacing them to
  // the bar + URL is just a matter of flipping the flag (the URL-sync effect writes the params).
  const explodeQuery = useCallback(() => setQueryCollapsed(false), []);

  // Fold an exploded query back to its pill, keeping the current (possibly edited) chips. The
  // URL-sync effect then strips the individual params, leaving only ?query=<slug>.
  const collapseQuery = useCallback(() => setQueryCollapsed(true), []);

  // Load a saved query's stored filters as editable chips and bind to it (so Save can overwrite it).
  // Replaces the current filters. The URL-sync effect writes the chip params and ?query=<slug>.
  const expandQueryToChips = useCallback(
    (slug: string, filters: Record<string, unknown>) => {
      setActiveQuerySlug(slug);
      loadLanes(filtersToLanes(filters));
      setQueryCollapsed(false);
    },
    [filtersToLanes, loadLanes]
  );

  // On a collapsed load the URL carries only ?query=<slug>, so committed lanes are empty and the
  // list wouldn't filter. Resolve the saved query and populate the lanes once.
  const { data: resolvedQuery } = useQueriesRetrieve(activeQuerySlug ?? "", undefined, {
    query: { enabled: queryCollapsed && !!activeQuerySlug },
  });
  const resolvedSlugRef = useRef<string | null>(null);
  useEffect(() => {
    if (!queryCollapsed || !activeQuerySlug || !resolvedQuery) return;
    if (resolvedSlugRef.current === activeQuerySlug) return;
    if (committedLanes.some(l => l.chips.length > 0)) {
      resolvedSlugRef.current = activeQuerySlug;
      return;
    }
    loadLanes(filtersToLanes((resolvedQuery.filters ?? {}) as Record<string, unknown>));
    resolvedSlugRef.current = activeQuerySlug;
  }, [queryCollapsed, activeQuerySlug, resolvedQuery, committedLanes, filtersToLanes, loadLanes]);

  // addChip: draft only (no commit — applied on explicit apply/enter/esc)
  const addChip = useCallback(
    (chip: Omit<FilterChip, "id">) => {
      if (mode === ImageListMode.SIMILAR) similarity.setModeBrowse();
      const newChip = { ...chip, id: genChipId() };
      setLanes(prev => prev.map(l => (l.id === activeLaneId ? { ...l, chips: [...l.chips, newChip] } : l)));
    },
    [mode, similarity, activeLaneId]
  );

  // removeChip: commits immediately (direct user action like clicking X on a chip)
  const removeChip = useCallback((id: string) => {
    const updater = (prev: FilterLane[]) => prev.map(l => ({ ...l, chips: l.chips.filter(c => c.id !== id) }));
    setLanes(updater);
    setCommittedLanes(updater);
  }, []);

  // removeChipDraft: draft only (used by multi-select toggle — committed on apply)
  const removeChipDraft = useCallback((id: string) => {
    setLanes(prev => prev.map(l => ({ ...l, chips: l.chips.filter(c => c.id !== id) })));
  }, []);

  const clearChips = useCallback(() => {
    const updater = (prev: FilterLane[]) => prev.map(l => (l.id === activeLaneId ? { ...l, chips: [] } : l));
    setLanes(updater);
    setCommittedLanes(updater);
  }, [activeLaneId]);

  // commitFilters: sync draft → committed (called by hook on apply/enter/esc)
  const commitFilters = useCallback(() => {
    setLanes(currentLanes => {
      setCommittedLanes([...currentLanes]);
      return currentLanes;
    });
  }, []);

  const addLane = useCallback(() => {
    const newLane = createEmptyLane();
    setLanes(prev => [...prev, newLane]);
    setActiveLaneId(newLane.id);
  }, []);

  const removeLane = useCallback(
    (id: string) => {
      setLanes(prev => {
        const next = prev.filter(l => l.id !== id);
        if (next.length === 0) {
          const fresh = createEmptyLane();
          setActiveLaneId(fresh.id);
          setCommittedLanes([fresh]);
          return [fresh];
        }
        if (activeLaneId === id) setActiveLaneId(next[0].id);
        setCommittedLanes(next);
        return next;
      });
    },
    [activeLaneId]
  );

  const toggleLaneNegated = useCallback((id: string) => {
    const updater = (prev: FilterLane[]) => prev.map(l => (l.id === id ? { ...l, negated: !l.negated } : l));
    setLanes(updater);
    setCommittedLanes(updater);
  }, []);

  const clearAllLanes = useCallback(() => {
    const fresh = createEmptyLane();
    setLanes([fresh]);
    setCommittedLanes([fresh]);
    setActiveLaneId(fresh.id);
  }, []);

  // Single writer for the whole URL query string (filters, ?query=, and similarity). One effect that
  // owns every param — built from the updater's `prev` (the latest params, never a stale closure) —
  // means the two writers can't clobber each other, which was resetting filters (esp. on Safari).
  useEffect(() => {
    setSearchParams(prev => {
      const newParams = new URLSearchParams(prev);
      // Remove only filter-related params (not similarity/mode params)
      for (const key of lanesToAllFilterParamKeys(committedLanes)) newParams.delete(key);
      // Set current filter params — but while collapsed the URL shows only ?query=<slug>, so the
      // individual params stay stripped (the filters live in committed lanes for fetching only).
      if (!queryCollapsed) {
        for (const [key, value] of Object.entries(committedFilterParams)) newParams.set(key, value);
      }
      // Mirror the bound-query marker (this effect is the sole writer of ?query=)
      if (activeQuerySlug) newParams.set("query", activeQuerySlug);
      else newParams.delete("query");
      // Similarity params: present only in similar mode, cleared otherwise
      const sim = mode === ImageListMode.SIMILAR;
      if (sim && similarity.similarImageId) newParams.set("similar", similarity.similarImageId);
      else newParams.delete("similar");
      if (sim && similarity.similarText) newParams.set("similarText", similarity.similarText);
      else newParams.delete("similarText");
      if (sim && similarity.similarFile) newParams.set("similarFile", "true");
      else newParams.delete("similarFile");
      if (sim && similarity.similarVector) newParams.set("similarVector", "true");
      else newParams.delete("similarVector");
      return newParams;
    });
  }, [
    committedFilterParams,
    activeQuerySlug,
    queryCollapsed,
    mode,
    similarity.similarImageId,
    similarity.similarText,
    similarity.similarFile,
    similarity.similarVector,
  ]);

  // -------------------- Fetching image list --------------------

  useEffect(() => {
    setImages([]);
    setImagesNextUrl(null);
  }, [mode, similarity.similarImageId, similarity.similarText, similarity.similarFile, similarity.similarVector]);

  // This provider is mounted by MainLayout, which wraps every page (images,
  // datasets, groups, group-types). The image list/count are only ever rendered
  // on the image LIST route, so gate the network queries on that — otherwise the
  // global, unfiltered list + count fire needlessly on group/dataset pages.
  const { pathname } = useLocation();
  const onImageListRoute = pathname === URLS.IMAGE_LIST();

  // Browse mode query (uses committed params so it doesn't fire on every multi-select tick)
  const browseQuery = useImagesList(
    {
      ...committedFilterParams,
      include_fields: LIST_INCLUDE_FIELDS,
      page_size: PAGE_SIZE,
    },
    {
      query: {
        enabled: onImageListRoute && mode === ImageListMode.BROWSE,
      },
    }
  );

  // Count query (same committed filters)
  const countQuery = useImagesCountRetrieve(
    { ...committedFilterParams },
    { query: { enabled: onImageListRoute && mode === ImageListMode.BROWSE } }
  );
  const totalCount = countQuery.data?.count ?? null;

  // Set up data when browse query completes
  useEffect(() => {
    if (mode === ImageListMode.BROWSE && browseQuery.data) {
      setImages(browseQuery.data.results);
      setImagesNextUrl(browseQuery.data.next);
    }
  }, [browseQuery.data, mode]);

  // Handle browse errors — keep a generic lead-in but append the backend's specific reason
  // (e.g. an invalid tag/group filter) when available, so a 400 is actionable.
  useEffect(() => {
    if (browseQuery.error && mode === ImageListMode.BROWSE) {
      const detail = extractApiError(browseQuery.error, "");
      toast.error(
        detail ? (
          <div>
            <div className="font-medium">Error loading images</div>
            <div className="text-sm opacity-80">{detail}</div>
          </div>
        ) : (
          "Error loading images"
        )
      );
      console.error(browseQuery.error);
    }
  }, [browseQuery.error, mode]);

  // Combine loading states
  const isLoadingImages = !!((mode === ImageListMode.BROWSE && browseQuery.isLoading) || similarity.isLoading);

  // Combine error states
  const isLoadingImagesError = !!((mode === ImageListMode.BROWSE && browseQuery.isError) || similarity.isError);

  // next page function
  const loadNextPage = async () => {
    if (mode === ImageListMode.BROWSE) {
      if (!imagesNextUrl) {
        return;
      }
      setIsLoadingNextPage(true);
      setIsLoadingNextPageError(false);
      axiosInstance<PaginatedOSImage>({
        method: "GET",
        url: imagesNextUrl,
      })
        .then(response => {
          const { results } = response;
          setImages([...images, ...results]);
          setImagesNextUrl(response.next);
        })
        .catch(e => {
          toast.error("Error loading next page of images");
          console.error(e);
          setIsLoadingNextPageError(true);
        })
        .finally(() => {
          setIsLoadingNextPage(false);
        });
    }
  };

  // -------------------- Return --------------------
  return (
    <ImageListDataContext.Provider
      value={{
        // image list
        images,
        isLoadingImages,
        isLoadingImagesError,
        hasNextPage: imagesNextUrl !== null,
        loadNextPage,
        isLoadingNextPage,
        isLoadingNextPageError,
        // mode
        mode,
        setModeBrowse: similarity.setModeBrowse,
        // similarity search
        setModeSimilarImage: (imageId: string) => {
          clearAllLanes();
          similarity.setModeSimilarImage(imageId);
        },
        similarImage: similarity.similarImage,
        setModeSimilarText: (text: string) => {
          clearAllLanes();
          similarity.setModeSimilarText(text);
        },
        similarText: similarity.similarText,
        setModeSimilarFile: (file: File) => {
          clearAllLanes();
          similarity.setModeSimilarFile(file);
        },
        similarFile: similarity.similarFile,
        setModeSimilarVector: (vector: string) => {
          clearAllLanes();
          similarity.setModeSimilarVector(vector);
        },
        similarVector: similarity.similarVector,
        // selecting
        isSelecting: selection.isSelecting,
        setIsSelecting: selection.setIsSelecting,
        selectedImages: selection.selectedImages,
        selectedImageObjects: selection.selectedImageObjects,
        toggleSelectedImage: selection.toggleSelectedImage,
        addSelectedImages: selection.addSelectedImages,
        clearSelectedImages: selection.clearSelectedImages,
        // grid
        gridColumns,
        setGridColumns: handleSetGridColumns,
        // filters
        chips,
        addChip,
        removeChip,
        removeChipDraft,
        clearChips,
        // lanes
        lanes,
        activeLaneId,
        setActiveLane: setActiveLaneId,
        addLane,
        removeLane,
        toggleLaneNegated,
        clearAllLanes,
        isAdvancedFilter: advancedFilter,
        // commit
        commitFilters,
        committedFilterParams,
        // saved query
        activeQuerySlug,
        queryCollapsed,
        bindQuery,
        clearActiveQuery,
        collapseToQuery,
        explodeQuery,
        collapseQuery,
        expandQueryToChips,
        // count
        totalCount,
        // refetch
        refetchImages: () => browseQuery.refetch(),
      }}
    >
      {children}
    </ImageListDataContext.Provider>
  );
}

// hook to use the image data context
export function useImageListData() {
  const context = useContext(ImageListDataContext);
  if (context === undefined) {
    throw new Error("useImageListData must be used within a ImageListDataContext");
  }
  return context;
}
