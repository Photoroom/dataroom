import { useQuery } from "@tanstack/react-query";
import { useMemo } from "react";
import { axiosInstance } from "../../../api/axios";
import { useClassifiersList } from "../../../api/client";
import type { Classifier } from "../../../api/client.schemas";
import type { FacetsResponse } from "./useFacets";

const SCORED_CACHE_MS = 5 * 60 * 1000;
const EMPTY: Classifier[] = [];

/**
 * Classifier versions that have scores on at least one image, so a score
 * filter on them can match something. One unfiltered facets call checks
 * every classifier at once.
 */
export function useScoredClassifiers(enabled = true) {
  const { data: classifiersData } = useClassifiersList({ page_size: 100 }, { query: { enabled } });
  const classifiers = classifiersData?.results ?? EMPTY;
  const fields = classifiers.map(c => `clf:${c.slug_version}`).join(",");

  const { data: facets } = useQuery({
    queryKey: ["/api/images/facets/", "scored-classifiers", fields],
    queryFn: ({ signal }) =>
      axiosInstance<FacetsResponse>({ url: "/api/images/facets/", method: "GET", params: { fields }, signal }),
    enabled: enabled && !!fields,
    staleTime: SCORED_CACHE_MS,
  });

  return useMemo(
    () => (facets ? classifiers.filter(c => (facets[`clf:${c.slug_version}`]?.stats?.count ?? 0) > 0) : EMPTY),
    [classifiers, facets]
  );
}
