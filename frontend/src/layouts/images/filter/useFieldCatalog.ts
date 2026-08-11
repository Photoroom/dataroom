import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { axiosInstance } from "../../../api/axios";
import { FacetBucket } from "./useFacets";
import { FieldType, isCatalogField } from "./constants";

// The catalog is the global, unfiltered universe of values for a discrete field. It barely
// changes, so we cache it aggressively on the client and filter locally instead of refetching.
const CATALOG_CACHE_MS = 24 * 60 * 60 * 1000; // 1 day

// The react-query cache above is in-memory only — a full page load starts cold. This header
// opts into the backend's `cache_response` layer, which serves the (expensive, ~seconds at
// prod tag cardinality) aggregation from the server cache and lets the browser HTTP cache
// reuse the response across page loads.
const CATALOG_HTTP_CACHE_SECONDS = 15 * 60;

export interface FieldCatalog {
  /** Every distinct value with its global (unfiltered) doc count. */
  values: FacetBucket[];
  /** Total number of distinct values (exact). */
  total: number;
  /** True if the backend hit its safety cap and the list is incomplete. */
  truncated: boolean;
}

interface CatalogResponse {
  [field: string]: FieldCatalog;
}

const catalogQueryKey = (field: string) => ["/api/images/field_catalog/", field] as const;

function fetchCatalog(field: string, signal?: AbortSignal): Promise<CatalogResponse> {
  return axiosInstance<CatalogResponse>({
    url: "/api/images/field_catalog/",
    method: "GET",
    params: { fields: field },
    headers: { "Cache-Control": `max-age=${CATALOG_HTTP_CACHE_SECONDS}` },
    signal,
  });
}

const EMPTY: FacetBucket[] = [];

/**
 * Load the complete value catalog for a discrete field, cached on the client for a day.
 * Returns empty/disabled for fields that don't support a catalog (numeric, date, enum, etc.).
 */
export function useFieldCatalog(field: string | null, fieldType?: FieldType) {
  const enabled = !!field && isCatalogField(field, fieldType);
  const query = useQuery({
    queryKey: catalogQueryKey(field ?? ""),
    queryFn: ({ signal }) => fetchCatalog(field!, signal),
    enabled,
    staleTime: CATALOG_CACHE_MS,
    gcTime: CATALOG_CACHE_MS,
    retry: (failureCount, error) => {
      const status = (error as { response?: { status?: number } })?.response?.status;
      if (status === 404 || status === 403 || status === 400) return false;
      return failureCount < 2;
    },
  });

  const data = field ? query.data?.[field] : undefined;
  return {
    values: data?.values ?? EMPTY,
    total: data?.total ?? 0,
    truncated: data?.truncated ?? false,
    isLoading: enabled && query.isLoading,
    enabled,
  };
}

/**
 * Overlay filter-aware facet counts onto the catalog's global value list. The catalog stays
 * the source of truth for WHICH values exist; the facet buckets (computed with the active
 * filters applied) provide the counts. Values absent from the facet response show 0 — exact
 * unless the filtered result has more distinct values than the facets terms-agg size
 * (FACET_TERMS_SIZE, kept equal to the catalog's own 50k safety cap).
 */
export function overlayFacetCounts(catalogValues: FacetBucket[], facetBuckets: FacetBucket[]): FacetBucket[] {
  const counts = new Map(facetBuckets.map(b => [String(b.key), b.doc_count]));
  const merged = catalogValues.map(v => ({ key: v.key, doc_count: counts.get(String(v.key)) ?? 0 }));
  // Values created after the catalog snapshot may exist only in the facet response — keep them.
  const known = new Set(catalogValues.map(v => String(v.key)));
  for (const b of facetBuckets) {
    if (!known.has(String(b.key))) merged.push(b);
  }
  return merged;
}

// Common fields worth warming on page load so the search bar & sidebar are instant.
const PREFETCH_FIELDS = ["source", "tag", "dataset"];

/** Prefetch the common catalogs once so they're cached before the user opens a filter. */
export function usePrefetchCommonCatalogs() {
  const queryClient = useQueryClient();
  useEffect(() => {
    for (const field of PREFETCH_FIELDS) {
      queryClient.prefetchQuery({
        queryKey: catalogQueryKey(field),
        queryFn: ({ signal }) => fetchCatalog(field, signal),
        staleTime: CATALOG_CACHE_MS,
        gcTime: CATALOG_CACHE_MS,
      });
    }
  }, [queryClient]);
}
