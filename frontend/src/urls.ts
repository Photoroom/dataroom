const getSearchParamsString = (searchParams?: URLSearchParams) => (searchParams ? "?" + searchParams.toString() : "");

export const URLS = {
  IMAGE_LIST: (searchParams?: URLSearchParams) => `/images${getSearchParamsString(searchParams)}`,
  IMAGE_DETAIL: (id: string, searchParams?: URLSearchParams) => `/images/${id}${getSearchParamsString(searchParams)}`,
  DATASET_LIST: (searchParams?: URLSearchParams) => `/datasets${getSearchParamsString(searchParams)}`,
  DATASET_DETAIL: (slug: string) => `/datasets/${slug}`,
  SETTINGS: "/settings",
};
