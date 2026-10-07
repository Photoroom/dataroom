import { Classifier } from "./api/client.schemas";

const getSearchParamsString = (searchParams?: URLSearchParams) => (searchParams ? "?" + searchParams.toString() : "");

export const URLS = {
  IMAGE_LIST: (searchParams?: URLSearchParams) => `/images${getSearchParamsString(searchParams)}`,
  IMAGE_DETAIL: (id: string, searchParams?: URLSearchParams) => `/images/${id}${getSearchParamsString(searchParams)}`,
  DATASET_LIST: (searchParams?: URLSearchParams) => `/datasets${getSearchParamsString(searchParams)}`,
  DATASET_DETAIL: (slug: string, version: string | number) => `/datasets/${slug}/${version}`,
  CLASSIFIER_LIST: (searchParams?: URLSearchParams) => `/classifiers${getSearchParamsString(searchParams)}`,
  CLASSIFIER_DETAIL: (slug: string, version: string | number) => `/classifiers/${slug}/${version}`,
  CLASSIFIER_ANNOTATE: (slug: string, version: string | number, searchParams?: URLSearchParams) =>
    `/classifiers/${slug}/${version}/annotate${getSearchParamsString(searchParams)}`,
  CLASSIFIER_ANNOTATE_IMAGE: (slug: string, version: string | number, id: string, searchParams?: URLSearchParams) =>
    `/classifiers/${slug}/${version}/annotate/${id}${getSearchParamsString(searchParams)}`,
  GROUP_LIST: (searchParams?: URLSearchParams) => `/groups${getSearchParamsString(searchParams)}`,
  GROUP_DETAIL: (id: string) => `/groups/${id}`,
  GROUP_TYPE_LIST: (searchParams?: URLSearchParams) => `/group-types${getSearchParamsString(searchParams)}`,
  SETTINGS: "/settings",
};

export const datasetUrl = (slugVersion: string) => {
  const [slug, version] = slugVersion.split("/");
  return URLS.DATASET_DETAIL(slug, version);
};

/** Browsing a side leads into labelling it, so an editable classifier sends you
 * to the annotate workspace with the filter already applied. A locked one
 * cannot be labelled, so it goes to the plain images view. */
export const browseUrl = (classifier: Classifier, datasets: string[]) => {
  const params = new URLSearchParams({ datasets: datasets.join(",") });
  if (classifier.is_frozen) return URLS.IMAGE_LIST(params);
  return `${URLS.CLASSIFIER_ANNOTATE(classifier.slug, classifier.version)}?${params}`;
};
