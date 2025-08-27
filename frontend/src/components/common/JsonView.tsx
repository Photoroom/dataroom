import React, { useMemo, useState } from "react";
import { twMerge } from "tailwind-merge";

interface JsonViewProps {
  value: unknown;
  className?: string;
  initiallyCollapsed?: boolean;
}

export const JsonView: React.FC<JsonViewProps> = ({ value, className, initiallyCollapsed = true }) => {
  const [isOpen, setIsOpen] = useState<boolean>(!initiallyCollapsed);

  const preview = useMemo(() => {
    try {
      if (Array.isArray(value)) {
        if (value.length === 0) return "[]";
        const first = value[0];
        if (typeof first === "object" && first !== null) return `[${value.length} objects]`;
        const arr = value as Array<string | number | boolean | null | undefined>;
        const sample = arr
          .slice(0, 10)
          .map(v => (v === undefined || v === null ? "<empty>" : String(v)))
          .join(", ");
        return arr.length > 10 ? `${sample}, …` : sample;
      }
      if (typeof value === "object" && value !== null) {
        const keys = Object.keys(value as Record<string, unknown>);
        if (keys.length === 0) return "{}";
        return `{ ${keys.slice(0, 5).join(", ")}${keys.length > 5 ? ", …" : ""} }`;
      }
      if (typeof value === "boolean") return `<${String(value)}>`;
      if (value === undefined || value === null || value === "") return "<empty>";
      return String(value);
    } catch {
      return "<unserializable>";
    }
  }, [value]);

  const json = useMemo(() => {
    try {
      return JSON.stringify(value, null, 2);
    } catch {
      return String(value);
    }
  }, [value]);

  return (
    <div className={twMerge("text-sm", className)}>
      <div className="flex flex-col items-start gap-2">
        <span className="break-all">{preview}</span>
        <button
          type="button"
          onClick={() => setIsOpen(v => !v)}
          className="px-2 py-0.5 text-xs rounded border border-black/10 dark:border-white/10 hover:bg-black/5 dark:hover:bg-white/5 inline-flex whitespace-nowrap shrink-0"
          aria-expanded={isOpen}
        >
          {isOpen ? "Hide value" : "Show value"}
        </button>
      </div>
      {isOpen && (
        <pre className="mt-2 text-xs whitespace-pre-wrap break-all p-2 rounded bg-black/5 dark:bg-white/5">{json}</pre>
      )}
    </div>
  );
};
