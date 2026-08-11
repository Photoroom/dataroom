import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { axiosInstance } from "../../../api/axios";
import { FilterChip } from "../../../context/ImageListDataContext";
import { chipsToApiParamsExcluding } from "../../../context/filterUtils";

export interface FacetBucket {
  key: string;
  doc_count: number;
}

export interface FacetNumeric {
  stats: { min: number; max: number; count: number; avg: number; sum: number } | null;
  histogram: { key: number; doc_count: number }[];
}

export interface FacetsResponse {
  [field: string]: { buckets?: FacetBucket[] } & Partial<FacetNumeric>;
}

function fetchFacets(
  fields: string,
  excludeField: string | undefined,
  filterParams: Record<string, string>,
  signal?: AbortSignal
): Promise<FacetsResponse> {
  const params: Record<string, string> = {
    ...filterParams,
    fields,
  };
  if (excludeField) params.exclude_field = excludeField;

  return axiosInstance<FacetsResponse>({ url: "/api/images/facets/", method: "GET", params, signal });
}

export function useFacets(chips: FilterChip[], selectedField: string | null, enabled: boolean) {
  // Self-exclusion: exclude the selected field so toggling its values
  // doesn't change facet params, but removing chips for OTHER fields does
  // update counts — which is what we want.
  const filterParams = useMemo(() => {
    if (!selectedField) return {};
    return chipsToApiParamsExcluding(chips, selectedField);
  }, [chips, selectedField]);

  const queryKey = useMemo(
    () => ["/api/images/facets/", selectedField, filterParams] as const,
    [selectedField, filterParams]
  );

  const query = useQuery({
    queryKey,
    queryFn: ({ signal }) => fetchFacets(selectedField!, selectedField ?? undefined, filterParams, signal),
    enabled: enabled && !!selectedField,
    placeholderData: prev => prev, // keep previous data while loading
    staleTime: 10_000,
    retry: (failureCount, error) => {
      const status = (error as { response?: { status?: number } })?.response?.status;
      if (status === 404 || status === 403) return false;
      return failureCount < 2;
    },
  });

  const facetData = query.data?.[selectedField ?? ""];
  return {
    buckets: facetData?.buckets ?? [],
    stats: facetData?.stats ?? null,
    histogram: facetData?.histogram ?? [],
    isLoading: query.isLoading,
  };
}
