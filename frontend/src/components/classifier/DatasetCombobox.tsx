import React, { useEffect, useRef, useState } from "react";
import { twMerge } from "tailwind-merge";
import { useDatasetsList } from "../../api/client";
import { formWidgetClassName } from "../forms/TextField";

/** Type-to-search picker for a dataset, searched server-side.
 *
 * Datasets a classifier owns are internal and excluded from the listing, so
 * they cannot be picked here by accident. That is deliberate: those
 * are edited by labelling rather than by being attached.
 */
export const DatasetCombobox: React.FC<{
  value: string;
  onChange: (value: string) => void;
  placeholder?: string;
}> = ({ value, onChange, placeholder = "Search datasets..." }) => {
  const [term, setTerm] = useState(value);
  const [debounced, setDebounced] = useState(value);
  const [isOpen, setIsOpen] = useState(false);
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => setTerm(value), [value]);

  // One request per pause in typing, not per keystroke.
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(term), 250);
    return () => window.clearTimeout(timer);
  }, [term]);

  useEffect(() => {
    const onPointerDown = (event: PointerEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) setIsOpen(false);
    };
    window.addEventListener("pointerdown", onPointerDown);
    return () => window.removeEventListener("pointerdown", onPointerDown);
  }, []);

  const { data } = useDatasetsList({ search: debounced || undefined, type: "single_image", page_size: 20 });
  const options = data?.results ?? [];

  return (
    <div className="relative" ref={containerRef}>
      <input
        className={formWidgetClassName}
        value={term}
        onChange={e => {
          setTerm(e.target.value);
          onChange(e.target.value);
          setIsOpen(true);
        }}
        onFocus={() => setIsOpen(true)}
        placeholder={placeholder}
        autoComplete="off"
      />
      {isOpen && (
        <ul
          className={twMerge(
            "absolute z-10 left-0 right-0 mt-1 max-h-56 overflow-auto rounded-lg shadow-lg",
            "bg-white dark:bg-dark-100 border border-black/10 dark:border-white/10"
          )}
        >
          {options.length === 0 && <li className="px-2.5 py-2 text-xs opacity-50">No matches</li>}
          {options.map(dataset => (
            <li key={dataset.slug_version}>
              <button
                type="button"
                onClick={() => {
                  onChange(dataset.slug_version);
                  setTerm(dataset.slug_version);
                  setIsOpen(false);
                }}
                className={twMerge(
                  "w-full text-left px-2.5 py-1.5 text-sm cursor-pointer hover:bg-black/5 dark:hover:bg-white/10",
                  dataset.slug_version === value ? "bg-brand-500/10" : ""
                )}
              >
                <span className="font-mono text-xs">{dataset.slug_version}</span>
                <span className="opacity-50 text-xs ml-2">
                  {dataset.name}, {dataset.group_count} groups
                </span>
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};
