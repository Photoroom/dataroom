import Axios, { AxiosRequestConfig } from "axios";

// DRF + django-filter expect comma-separated lists (e.g. ?type=a,b,c) rather
// than repeated keys (?type=a&type=b). Override the default array serializer.
const csvParamsSerializer = (params: Record<string, unknown>): string => {
  const parts: string[] = [];
  for (const [key, value] of Object.entries(params)) {
    if (value === undefined || value === null) continue;
    const encoded = encodeURIComponent(key);
    if (Array.isArray(value)) {
      const filtered = value.filter(v => v !== undefined && v !== null);
      if (!filtered.length) continue;
      parts.push(`${encoded}=${filtered.map(v => encodeURIComponent(String(v))).join(",")}`);
    } else {
      parts.push(`${encoded}=${encodeURIComponent(String(value))}`);
    }
  }
  return parts.join("&");
};

export const AXIOS_INSTANCE = Axios.create({ paramsSerializer: csvParamsSerializer });

export const getCsrfToken = () => {
  return document.querySelector('meta[name="csrf-token"]')?.getAttribute("content") || "";
};

export const axiosInstance = <T>(config: AxiosRequestConfig, options?: AxiosRequestConfig): Promise<T> => {
  const source = Axios.CancelToken.source();
  const token = getCsrfToken();
  if (token) {
    if (!config.headers) {
      config.headers = {};
    }
    config.headers["X-CSRFToken"] = token;
  }
  const promise = AXIOS_INSTANCE({
    ...config,
    ...options,
    cancelToken: source.token,
  }).then(({ data }) => data);

  // @ts-expect-error Promise type doesn't include cancel property, but we're extending it
  promise.cancel = () => {
    source.cancel("Query was cancelled");
  };

  return promise;
};
