import React, { useEffect, useMemo, useRef, useState } from "react";
import { twMerge } from "tailwind-merge";
import { useDatasetsList, useQueriesList, useTagsList, useImagesFieldCatalogRetrieve } from "../../api/client";
import { formWidgetClassName } from "../forms/TextField";

export interface TargetOption {
  value: string;
  hint?: string;
}

/** Type-to-search picker for an apply target.
 *
 * Each target kind has its own catalogue, so the search goes to the matching
 * endpoint server-side rather than filtering a list the browser happens to
 * hold: datasets, tags and saved queries all take a ``search`` term. Sources
 * are the exception — the field catalogue returns every distinct value in one
 * bounded response, so those filter locally.
 */
export const TargetCombobox: React.FC<{
  targetType: string;
  value: string;
  onChange: (value: string) => void;
}> = ({ targetType, value, onChange }) => {
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

  // Close when the click lands outside.
  useEffect(() => {
    const onPointerDown = (event: PointerEvent) => {
      if (containerRef.current && !containerRef.current.contains(event.target as Node)) setIsOpen(false);
    };
    window.addEventListener("pointerdown", onPointerDown);
    return () => window.removeEventListener("pointerdown", onPointerDown);
  }, []);

  const search = debounced || undefined;
  const { data: datasets } = useDatasetsList(
    { search, page_size: 20 },
    { query: { enabled: targetType === "dataset" } }
  );
  const { data: tags } = useTagsList({ search, page_size: 20 }, { query: { enabled: targetType === "tag" } });
  const { data: queries } = useQueriesList({ search, page_size: 20 }, { query: { enabled: targetType === "query" } });
  const { data: catalog } = useImagesFieldCatalogRetrieve(
    { fields: "source" },
    { query: { enabled: targetType === "source" } }
  );

  const options: TargetOption[] = useMemo(() => {
    if (targetType === "dataset") {
      return (datasets?.results ?? []).map(dataset => ({
        value: dataset.slug_version,
        hint: `${dataset.name} · ${dataset.group_count} groups`,
      }));
    }
    if (targetType === "tag") {
      return (tags?.results ?? []).map(tag => ({ value: tag.name }));
    }
    if (targetType === "query") {
      return (queries?.results ?? []).map(query => ({ value: query.slug, hint: query.name }));
    }
    if (targetType === "source") {
      // The catalog endpoint is typed as void by the generated client (its
      // response shape is dynamic per requested field), so read it structurally.
      const catalogue = catalog as unknown as { source?: { values?: { key: string; doc_count: number }[] } };
      const values = catalogue?.source?.values ?? [];
      const needle = (debounced || "").toLowerCase();
      return values
        .filter(entry => entry.key.toLowerCase().includes(needle))
        .slice(0, 20)
        .map(entry => ({ value: entry.key, hint: `${entry.doc_count} images` }));
    }
    return [];
  }, [targetType, datasets, tags, queries, catalog, debounced]);

  const pick = (option: TargetOption) => {
    onChange(option.value);
    setTerm(option.value);
    setIsOpen(false);
  };

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
        placeholder={targetType === "dataset" ? "Search datasets..." : `Search ${targetType}s...`}
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
          {options.map(option => (
            <li key={option.value}>
              <button
                type="button"
                onClick={() => pick(option)}
                className={twMerge(
                  "w-full text-left px-2.5 py-1.5 text-sm cursor-pointer",
                  "hover:bg-black/5 dark:hover:bg-white/10",
                  option.value === value ? "bg-brand-500/10" : ""
                )}
              >
                <span className="font-mono text-xs">{option.value}</span>
                {option.hint && <span className="opacity-50 text-xs ml-2">{option.hint}</span>}
              </button>
            </li>
          ))}
        </ul>
      )}
    </div>
  );
};
