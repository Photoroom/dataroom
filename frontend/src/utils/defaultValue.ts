export default function defaultValue<T>(
  value: T,
  defaultValue: string = "<empty>",
  emptyValues: unknown[] = [undefined, null, ""]
): T | string {
  if (emptyValues.includes(value)) {
    return defaultValue;
  }
  if (typeof value === "boolean") {
    return "<" + String(value) + ">";
  }
  return value;
}
