const getSearchParamsString = (searchParams?: URLSearchParams) => (searchParams ? "?" + searchParams.toString() : "");

export const URLS = {
  IMAGE_LIST: (searchParams?: URLSearchParams) => `/images${getSearchParamsString(searchParams)}`,
  IMAGE_DETAIL: (id: string, searchParams?: URLSearchParams) => `/images/${id}${getSearchParamsString(searchParams)}`,
  DATASET_LIST: (searchParams?: URLSearchParams) => `/datasets${getSearchParamsString(searchParams)}`,
  DATASET_DETAIL: (slug: string, version: string | number) => `/datasets/${slug}/${version}`,
  GROUP_LIST: (searchParams?: URLSearchParams) => `/groups${getSearchParamsString(searchParams)}`,
  GROUP_DETAIL: (id: string) => `/groups/${id}`,
  GROUP_TYPE_LIST: (searchParams?: URLSearchParams) => `/group-types${getSearchParamsString(searchParams)}`,
  SETTINGS: "/settings",
};
