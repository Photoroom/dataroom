// Pull a human-readable message out of a DRF error response.
//
// DRF returns errors in a few shapes: a bare string, a bare list of strings (e.g. a
// ValidationError raised from a filter method -> ["One or more tags do not exist: 1"]),
// or an object keyed by field / "detail" / "non_field_errors". This normalizes all of them.
export function extractApiError(error: unknown, fallback = "Something went wrong"): string {
  const data = (error as { response?: { data?: unknown } })?.response?.data;

  if (typeof data === "string") return data;
  if (Array.isArray(data) && typeof data[0] === "string") return data[0];

  if (data && typeof data === "object") {
    const obj = data as Record<string, unknown>;
    // Prefer well-known keys, then fall back to the first string-ish value (e.g. {tags: [...]}).
    const keys = ["detail", "non_field_errors", "slug", "name", "filters", ...Object.keys(obj)];
    for (const key of keys) {
      const value = obj[key];
      if (typeof value === "string") return value;
      if (Array.isArray(value) && typeof value[0] === "string") return value[0];
    }
  }

  return fallback;
}
