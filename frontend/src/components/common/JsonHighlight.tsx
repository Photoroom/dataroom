import React, { useMemo } from "react";
import { twMerge } from "tailwind-merge";

interface JsonHighlightProps {
  value: unknown;
  className?: string;
  /** Recursively parse string values that are themselves JSON, so nested JSON renders unescaped. */
  deep?: boolean;
}

/** Unwrap strings that contain a JSON object/array into the parsed value, recursively. */
function deepParse(value: unknown, depth = 0): unknown {
  if (depth > 8) return value;
  if (typeof value === "string") {
    const trimmed = value.trim();
    if (trimmed.startsWith("{") || trimmed.startsWith("[")) {
      try {
        const parsed = JSON.parse(trimmed);
        if (parsed !== null && typeof parsed === "object") {
          return deepParse(parsed, depth + 1);
        }
      } catch {
        // not JSON — leave the string as-is
      }
    }
    return value;
  }
  if (Array.isArray(value)) {
    return value.map(v => deepParse(v, depth + 1));
  }
  if (value !== null && typeof value === "object") {
    return Object.fromEntries(
      Object.entries(value as Record<string, unknown>).map(([k, v]) => [k, deepParse(v, depth + 1)])
    );
  }
  return value;
}

const TOKEN_RE =
  /("(?:\\u[a-zA-Z0-9]{4}|\\[^u]|[^\\"])*"(?:\s*:)?|\b(?:true|false|null)\b|-?\d+(?:\.\d*)?(?:[eE][+-]?\d+)?)/g;

// Each token type gets its own hue so structure is readable at a glance.
// Shades are tuned per mode: 600–700 on the light (near-white) background,
// 300–400 on the dark background.
function classFor(token: string): string {
  if (token.startsWith('"')) {
    // Keys (a quoted string followed by a colon) vs. string values.
    return token.trimEnd().endsWith(":")
      ? "text-sky-700 dark:text-sky-300 font-semibold"
      : "text-emerald-700 dark:text-emerald-300";
  }
  if (token === "true" || token === "false") {
    return "text-fuchsia-700 dark:text-fuchsia-300 font-medium";
  }
  if (token === "null") {
    return "text-rose-600 dark:text-rose-400 italic";
  }
  // Numbers.
  return "text-amber-600 dark:text-amber-300";
}

/** Renders a value as pretty-printed JSON with lightweight syntax highlighting. */
export const JsonHighlight: React.FC<JsonHighlightProps> = ({ value, className, deep = false }) => {
  const json = useMemo(() => {
    try {
      return JSON.stringify(deep ? deepParse(value) : value, null, 2);
    } catch {
      return String(value);
    }
  }, [value, deep]);

  const nodes = useMemo(() => {
    const out: React.ReactNode[] = [];
    let lastIndex = 0;
    let match: RegExpExecArray | null;
    TOKEN_RE.lastIndex = 0;
    while ((match = TOKEN_RE.exec(json)) !== null) {
      if (match.index > lastIndex) {
        out.push(json.slice(lastIndex, match.index));
      }
      out.push(
        <span key={match.index} className={classFor(match[0])}>
          {match[0]}
        </span>
      );
      lastIndex = match.index + match[0].length;
    }
    if (lastIndex < json.length) {
      out.push(json.slice(lastIndex));
    }
    return out;
  }, [json]);

  return (
    <pre
      className={twMerge(
        "text-xs whitespace-pre-wrap break-all p-3 rounded-lg bg-black/5 dark:bg-white/5 overflow-auto",
        className
      )}
    >
      {nodes}
    </pre>
  );
};
