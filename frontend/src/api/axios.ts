import Axios, { AxiosRequestConfig } from "axios";

export const AXIOS_INSTANCE = Axios.create();

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
