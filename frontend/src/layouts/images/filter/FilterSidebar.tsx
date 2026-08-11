import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { twMerge } from "tailwind-merge";
import { useQuery, keepPreviousData } from "@tanstack/react-query";
import {
  ChevronUpIcon,
  ChevronDownIcon,
  XMarkIcon,
  PlusIcon,
  MagnifyingGlassIcon,
  BarsArrowDownIcon,
  BarsArrowUpIcon,
} from "@heroicons/react/20/solid";
import { isPinnedSection, useSidebarConfig } from "./useSidebarConfig";
import { useImageListData } from "../../../context/ImageListDataContext";
import { useStatsAttributesList } from "../../../api/client";
import { axiosInstance } from "../../../api/axios";
import { NUMERIC_FIELDS, DATE_FIELDS, parseLanesFromUrl } from "../../../context/filterUtils";
import { getFieldLabel, getAttrFieldType, BUILTIN_FIELDS, DUPLICATE_STATE_LABELS, FieldType } from "./constants";
import { Histogram } from "./Histogram";
import { DateRangePicker } from "./DateRangePicker";
import { RANGE_REPLACES } from "./numericConflicts";
import type { FacetsResponse } from "./useFacets";
import { useFieldCatalog, overlayFacetCounts } from "./useFieldCatalog";
import type { AttributeField } from "../../../api/client.schemas";

// All builtin fields are eligible for the sidebar add-section picker
const SIDEBAR_ELIGIBLE_BUILTINS = BUILTIN_FIELDS;

export const FilterSidebar: React.FC = () => {
  const { isVisible, sections, collapsed, toggleCollapsed, addSection, removeSection, width, setWidth } =
    useSidebarConfig();

  // Drag the right edge to resize: the sidebar is fixed at left 0, so the
  // pointer's x IS the wanted width (the context clamps it).
  const startResize = (e: React.PointerEvent) => {
    e.preventDefault();
    const onMove = (ev: PointerEvent) => setWidth(ev.clientX);
    const onUp = () => {
      window.removeEventListener("pointermove", onMove);
      window.removeEventListener("pointerup", onUp);
    };
    window.addEventListener("pointermove", onMove);
    window.addEventListener("pointerup", onUp);
  };
  const { committedFilterParams } = useImageListData();

  const { data: attributesData } = useStatsAttributesList();
  const indexedAttrs = useMemo(
    () => (attributesData || []).filter((a: AttributeField) => a.is_indexed && a.field_type !== "object"),
    [attributesData]
  );

  if (!isVisible) return null;

  return (
    <div
      style={{ width }}
      className={twMerge(
        "fixed left-0 bottom-0 z-20",
        "sm:top-14 top-[5.5rem]",
        "bg-light-100 dark:bg-dark-100",
        "border-r border-light-300 dark:border-dark-300",
        "overflow-y-auto flex flex-col",
        "hidden sm:flex"
      )}
    >
      {/* Resize handle — drag the right edge; width persists with the config */}
      <div
        onPointerDown={startResize}
        title="Drag to resize"
        className="absolute right-0 inset-y-0 w-1.5 cursor-col-resize z-30 hover:bg-brand-400/40 active:bg-brand-400/60 transition-colors"
      />
      {/* Header */}
      <div className="sticky top-0 z-10 bg-light-100 dark:bg-dark-100 px-3 py-2 flex items-center justify-between border-b border-light-300 dark:border-dark-300">
        <span className="text-[10px] font-semibold uppercase tracking-wider text-black/40 dark:text-white/40">
          Filters
        </span>
        <AddSectionButton sections={sections} onAdd={addSection} indexedAttrs={indexedAttrs} />
      </div>

      {/* Sections — pinned ones (dataset) have no remove affordance */}
      {sections.map(field => (
        <SidebarSection
          key={field}
          field={field}
          committedFilterParams={committedFilterParams}
          isCollapsed={!!collapsed[field]}
          onToggleCollapse={() => toggleCollapsed(field)}
          onRemove={isPinnedSection(field) ? undefined : () => removeSection(field)}
          indexedAttrs={indexedAttrs}
        />
      ))}

      {/* Empty state */}
      {sections.length === 0 && (
        <div className="px-3 py-6 text-center text-xs text-black/30 dark:text-white/30">
          No filter sections.
          <br />
          Click + to add one.
        </div>
      )}
    </div>
  );
};

// -------------------- Section --------------------

interface SidebarSectionProps {
  field: string;
  committedFilterParams: Record<string, string>;
  isCollapsed: boolean;
  onToggleCollapse: () => void;
  // absent for pinned sections — no remove affordance
  onRemove?: () => void;
  indexedAttrs: AttributeField[];
}

const MAX_VISIBLE_VALUES = 10;
const SHOW_MORE_STEP = 50;

const SidebarSection: React.FC<SidebarSectionProps> = ({
  field,
  committedFilterParams,
  isCollapsed,
  onToggleCollapse,
  onRemove,
  indexedAttrs,
}) => {
  const { lanes, addChip, removeChip, commitFilters } = useImageListData();

  const isDate = useMemo(() => DATE_FIELDS.has(field), [field]);

  // Field type for catalog detection (keyword attributes get a catalog; enum/numeric/etc. don't).
  const catalogFieldType = useMemo<FieldType | undefined>(() => {
    if (!field.startsWith("attr:")) return undefined;
    const attr = indexedAttrs.find(a => a.name === field.slice(5));
    return attr ? getAttrFieldType(attr) : undefined;
  }, [field, indexedAttrs]);

  // Unbounded discrete fields (source, tag, dataset, keyword attrs) load their full value
  // set once and cache it client-side (global counts, no user filters applied).
  const catalog = useFieldCatalog(field, catalogFieldType);
  const isCatalog = catalog.enabled;

  // Filters on OTHER fields change this section's counts. Reconstruct the committed chips
  // from the committed params (handles both flat params and the filter_lanes JSON form).
  const hasOtherFilters = useMemo(
    () =>
      parseLanesFromUrl(new URLSearchParams(committedFilterParams)).some(lane =>
        lane.chips.some(c => c.field !== field)
      ),
    [committedFilterParams, field]
  );

  // Fetch filter-aware facets with self-exclusion (skip date fields — no facets). Catalog
  // fields take their value list from the catalog, so facets are only needed for them — as
  // a count overlay — while filters on other fields are active.
  const facetsQuery = useQuery({
    queryKey: ["/api/images/facets/", field, committedFilterParams],
    queryFn: ({ signal }) =>
      axiosInstance<FacetsResponse>({
        url: "/api/images/facets/",
        method: "GET",
        params: { ...committedFilterParams, fields: field, exclude_field: field },
        signal,
      }),
    enabled: !isDate && (!isCatalog || hasOtherFilters),
    staleTime: 10_000,
    placeholderData: keepPreviousData,
  });

  // Discrete value list: catalog fields show the full cached value list with filter-aware
  // counts overlaid once facets load (global counts until then, and when no other filters
  // are active); everything else uses the filtered facet buckets directly.
  const facetData = useMemo<FacetsResponse[string] | undefined>(() => {
    if (!isCatalog) return facetsQuery.data?.[field];
    const filteredBuckets = hasOtherFilters ? facetsQuery.data?.[field]?.buckets : undefined;
    return { buckets: filteredBuckets ? overlayFacetCounts(catalog.values, filteredBuckets) : catalog.values };
  }, [isCatalog, hasOtherFilters, facetsQuery.data, field, catalog.values]);
  const discreteIsLoading = isCatalog ? catalog.isLoading : facetsQuery.isLoading;
  const label = getFieldLabel(field);

  // All chips across all lanes
  const allChips = useMemo(() => lanes.flatMap(l => l.chips), [lanes]);

  // Detect numeric field (builtin or attribute)
  const isNumeric = useMemo(() => {
    if (NUMERIC_FIELDS.has(field)) return true;
    if (field.startsWith("attr:")) {
      const attr = indexedAttrs.find(a => a.name === field.slice(5));
      return attr?.field_type === "number" || attr?.field_type === "integer";
    }
    return false;
  }, [field, indexedAttrs]);

  // Count active range chips for the header badge
  const activeRangeCount = useMemo(
    () => allChips.filter(c => c.field === field && RANGE_REPLACES.has(c.operator)).length,
    [allChips, field]
  );

  // Active values (eq) for non-numeric fields
  const activeValues = useMemo(
    () => new Set(allChips.filter(c => c.field === field && c.operator === "eq").map(c => c.value)),
    [allChips, field]
  );

  const badgeCount = isNumeric || isDate ? activeRangeCount : activeValues.size;

  // Body content based on field type
  let body: React.ReactNode = null;
  if (isNumeric) {
    body = (
      <NumericSectionBody
        field={field}
        facetData={facetData}
        allChips={allChips}
        addChip={addChip}
        removeChip={removeChip}
        commitFilters={commitFilters}
        isLoading={facetsQuery.isLoading}
      />
    );
  } else if (isDate) {
    body = (
      <DateSectionBody
        field={field}
        allChips={allChips}
        addChip={addChip}
        removeChip={removeChip}
        commitFilters={commitFilters}
      />
    );
  } else {
    body = (
      <DiscreteSectionBody
        field={field}
        facetData={facetData}
        allChips={allChips}
        addChip={addChip}
        removeChip={removeChip}
        commitFilters={commitFilters}
        indexedAttrs={indexedAttrs}
        isLoading={discreteIsLoading}
      />
    );
  }

  return (
    <div className="border-t border-black/10 dark:border-white/10">
      {/* Section header — matches right-sidebar Collapsible style */}
      <div className="flex items-center group">
        <button
          type="button"
          onClick={onToggleCollapse}
          className="flex-1 flex items-center justify-between px-3 py-3 cursor-pointer hover:bg-black/3 dark:hover:bg-white/3 transition-colors min-w-0"
        >
          <span className="flex items-center gap-1.5 min-w-0">
            <span className="uppercase text-xs tracking-wide opacity-80 group-hover:opacity-100 transition-opacity truncate">
              {label}
            </span>
            {/* Total distinct value count (catalog fields only) */}
            {isCatalog && catalog.total > 0 && (
              <span className="text-[10px] text-black/35 dark:text-white/35 tabular-nums shrink-0">
                {catalog.total.toLocaleString()}
              </span>
            )}
            {badgeCount > 0 && (
              <span className="text-[10px] font-bold text-brand-600 dark:text-brand-400 tabular-nums shrink-0">
                {badgeCount}
              </span>
            )}
          </span>
          {isCollapsed ? (
            <ChevronDownIcon className="size-4 opacity-60 group-hover:opacity-100 transition-opacity shrink-0" />
          ) : (
            <ChevronUpIcon className="size-4 opacity-60 group-hover:opacity-100 transition-opacity shrink-0" />
          )}
        </button>
        {onRemove && (
          <button
            type="button"
            onClick={onRemove}
            className="p-1 mr-1 opacity-0 group-hover:opacity-40 hover:!opacity-100 cursor-pointer transition-opacity shrink-0"
            title="Remove section"
          >
            <XMarkIcon className="size-3.5" />
          </button>
        )}
      </div>

      {/* Animated collapse — matches right-sidebar Collapsible */}
      <div
        className={twMerge(
          "grid transition-all ease-in-out",
          isCollapsed ? "grid-rows-[0fr] opacity-0" : "grid-rows-[1fr] opacity-100"
        )}
      >
        <div className="overflow-hidden">{body}</div>
      </div>
    </div>
  );
};

// -------------------- Numeric section body (histogram) --------------------

interface NumericSectionBodyProps {
  field: string;
  facetData: FacetsResponse[string] | undefined;
  allChips: import("../../../context/ImageListDataContext").FilterChip[];
  addChip: (chip: Omit<import("../../../context/ImageListDataContext").FilterChip, "id">) => void;
  removeChip: (id: string) => void;
  commitFilters: () => void;
  isLoading: boolean;
}

const NumericSectionBody: React.FC<NumericSectionBodyProps> = ({
  field,
  facetData,
  allChips,
  addChip,
  removeChip,
  commitFilters,
  isLoading,
}) => {
  const histogram = facetData?.histogram || [];
  const stats = facetData?.stats ?? null;

  // Range slider state
  const [rangeStart, setRangeStart] = useState<number | null>(null);
  const [rangeEnd, setRangeEnd] = useState<number | null>(null);
  const [dirty, setDirty] = useState(false);

  // Initialize from existing gte/lte chips (re-sync when chips change externally)
  const initKey = useRef<string>("");
  useEffect(() => {
    const gteChip = allChips.find(c => c.field === field && c.operator === "gte");
    const lteChip = allChips.find(c => c.field === field && c.operator === "lte");
    const key = `${gteChip?.value ?? ""}:${lteChip?.value ?? ""}`;
    if (key === initKey.current) return;
    initKey.current = key;
    setRangeStart(gteChip ? Number(gteChip.value) : null);
    setRangeEnd(lteChip ? Number(lteChip.value) : null);
    setDirty(false);
  }, [allChips, field]);

  const handleRangeChange = useCallback((start: number | null, end: number | null) => {
    setRangeStart(start);
    setRangeEnd(end);
    setDirty(true);
  }, []);

  const applyRange = useCallback(() => {
    if (!dirty) return;
    // Remove existing range-related chips for this field
    const toRemove = allChips.filter(c => c.field === field && RANGE_REPLACES.has(c.operator));
    for (const c of toRemove) removeChip(c.id);
    if (rangeStart !== null) addChip({ field, operator: "gte", value: String(rangeStart) });
    if (rangeEnd !== null) addChip({ field, operator: "lte", value: String(rangeEnd) });
    commitFilters();
    setDirty(false);
  }, [dirty, field, rangeStart, rangeEnd, allChips, removeChip, addChip, commitFilters]);

  const clearRange = useCallback(() => {
    const toRemove = allChips.filter(c => c.field === field && RANGE_REPLACES.has(c.operator));
    for (const c of toRemove) removeChip(c.id);
    setRangeStart(null);
    setRangeEnd(null);
    setDirty(false);
    initKey.current = ":";
  }, [allChips, field, removeChip]);

  const hasActiveRange = allChips.some(c => c.field === field && RANGE_REPLACES.has(c.operator));

  if (!stats || histogram.length === 0) {
    return (
      <div className="px-3 py-2 text-xs text-black/25 dark:text-white/25">{isLoading ? "Loading..." : "No data"}</div>
    );
  }

  return (
    <div className="pb-2">
      <Histogram
        bins={histogram}
        min={stats.min}
        max={stats.max}
        mode="range"
        rangeStart={rangeStart}
        rangeEnd={rangeEnd}
        onRangeChange={handleRangeChange}
        onApply={applyRange}
      />
      <div className="px-3 flex gap-1">
        {dirty && (
          <button
            type="button"
            onClick={applyRange}
            className={twMerge(
              "flex-1 py-1 rounded text-xs font-medium cursor-pointer transition-colors",
              "bg-brand-600 text-white hover:bg-brand-700",
              "dark:bg-brand-500 dark:hover:bg-brand-600"
            )}
          >
            Apply
          </button>
        )}
        {hasActiveRange && !dirty && (
          <button
            type="button"
            onClick={clearRange}
            className="flex-1 py-1 rounded text-xs cursor-pointer text-black/40 dark:text-white/40 hover:text-black/60 dark:hover:text-white/60 border border-light-300 dark:border-dark-300"
          >
            Clear
          </button>
        )}
      </div>
    </div>
  );
};

// -------------------- Date section body --------------------

interface DateSectionBodyProps {
  field: string;
  allChips: import("../../../context/ImageListDataContext").FilterChip[];
  addChip: (chip: Omit<import("../../../context/ImageListDataContext").FilterChip, "id">) => void;
  removeChip: (id: string) => void;
  commitFilters: () => void;
}

const DateSectionBody: React.FC<DateSectionBodyProps> = ({ field, allChips, addChip, removeChip, commitFilters }) => {
  const containerRef = useRef<HTMLDivElement>(null);
  const gteChip = allChips.find(c => c.field === field && c.operator === "gte");
  const lteChip = allChips.find(c => c.field === field && c.operator === "lte");

  const [fromDate, setFromDate] = useState(gteChip?.value ?? "");
  const [toDate, setToDate] = useState(lteChip?.value ?? "");
  const [dirty, setDirty] = useState(false);

  // Re-sync when chips change externally
  const initRef = useRef<string>("");
  useEffect(() => {
    const key = `${gteChip?.value ?? ""}:${lteChip?.value ?? ""}`;
    if (key === initRef.current) return;
    initRef.current = key;
    setFromDate(gteChip?.value ?? "");
    setToDate(lteChip?.value ?? "");
    setDirty(false);
  }, [gteChip, lteChip]);

  // Scroll into view when mounted (fixes issue when added at bottom of sidebar)
  useEffect(() => {
    containerRef.current?.scrollIntoView({ behavior: "smooth", block: "nearest" });
  }, []);

  const handleRangeChange = useCallback((start: string, end: string) => {
    setFromDate(start);
    setToDate(end);
    setDirty(true);
  }, []);

  const applyRange = useCallback(() => {
    if (!dirty) return;
    const toRemove = allChips.filter(c => c.field === field && RANGE_REPLACES.has(c.operator));
    for (const c of toRemove) removeChip(c.id);
    if (fromDate) addChip({ field, operator: "gte", value: fromDate });
    if (toDate) addChip({ field, operator: "lte", value: toDate });
    commitFilters();
    setDirty(false);
  }, [dirty, field, fromDate, toDate, allChips, removeChip, addChip, commitFilters]);

  const clearRange = useCallback(() => {
    const toRemove = allChips.filter(c => c.field === field && RANGE_REPLACES.has(c.operator));
    for (const c of toRemove) removeChip(c.id);
    setFromDate("");
    setToDate("");
    setDirty(false);
    initRef.current = ":";
  }, [allChips, field, removeChip]);

  const hasActiveRange = allChips.some(c => c.field === field && RANGE_REPLACES.has(c.operator));

  return (
    <div ref={containerRef} className="px-2 pb-3 space-y-2">
      <DateRangePicker startDate={fromDate} endDate={toDate} onChange={handleRangeChange} compact />
      <div className="flex gap-1 px-1">
        {dirty && (
          <button
            type="button"
            onClick={applyRange}
            className={twMerge(
              "flex-1 py-1 rounded text-xs font-medium cursor-pointer transition-colors",
              "bg-brand-600 text-white hover:bg-brand-700",
              "dark:bg-brand-500 dark:hover:bg-brand-600"
            )}
          >
            Apply
          </button>
        )}
        {hasActiveRange && !dirty && (
          <button
            type="button"
            onClick={clearRange}
            className="flex-1 py-1 rounded text-xs cursor-pointer text-black/40 dark:text-white/40 hover:text-black/60 dark:hover:text-white/60 border border-light-300 dark:border-dark-300"
          >
            Clear
          </button>
        )}
      </div>
    </div>
  );
};

// -------------------- Discrete section body (checkboxes) --------------------

interface DiscreteSectionBodyProps {
  field: string;
  facetData: FacetsResponse[string] | undefined;
  allChips: import("../../../context/ImageListDataContext").FilterChip[];
  addChip: (chip: Omit<import("../../../context/ImageListDataContext").FilterChip, "id">) => void;
  removeChip: (id: string) => void;
  commitFilters: () => void;
  indexedAttrs: AttributeField[];
  isLoading: boolean;
}

const DiscreteSectionBody: React.FC<DiscreteSectionBodyProps> = ({
  field,
  facetData,
  allChips,
  addChip,
  removeChip,
  commitFilters,
  indexedAttrs,
  isLoading,
}) => {
  const [search, setSearch] = useState("");
  const [visibleCount, setVisibleCount] = useState(MAX_VISIBLE_VALUES);
  // Sort by count: descending (most frequent first) by default, ascending to surface rare values.
  const [sortAsc, setSortAsc] = useState(false);

  // Reset pagination whenever the working set changes (typing a filter or flipping the sort).
  useEffect(() => setVisibleCount(MAX_VISIBLE_VALUES), [search, sortAsc]);

  const activeValues = useMemo(
    () => new Set(allChips.filter(c => c.field === field && c.operator === "eq").map(c => c.value)),
    [allChips, field]
  );
  const excludedValues = useMemo(
    () => new Set(allChips.filter(c => c.field === field && c.operator === "ne").map(c => c.value)),
    [allChips, field]
  );

  const isBooleanAttr = useMemo(() => {
    if (!field.startsWith("attr:")) return false;
    const attr = indexedAttrs.find(a => a.name === field.slice(5));
    return attr?.field_type === "boolean";
  }, [field, indexedAttrs]);

  const buckets = useMemo(() => {
    const raw = facetData?.buckets || [];
    const items: { key: string; label: string; count: number }[] = [];
    const seen = new Set<string>();

    for (const b of raw) {
      let key = String(b.key);
      let displayLabel = key;

      if (field === "duplicate_state") {
        displayLabel = DUPLICATE_STATE_LABELS[key] || key;
      } else if (isBooleanAttr) {
        key = key === "1" ? "true" : key === "0" ? "false" : key;
        displayLabel = key;
      }

      if (!seen.has(key)) {
        seen.add(key);
        items.push({ key, label: displayLabel, count: b.doc_count });
      }
    }

    for (const value of activeValues) {
      if (!seen.has(value)) {
        let displayLabel = value;
        if (field === "duplicate_state") {
          displayLabel = DUPLICATE_STATE_LABELS[value] || value;
        }
        items.push({ key: value, label: displayLabel, count: 0 });
      }
    }

    return items;
  }, [facetData, field, isBooleanAttr, activeValues]);

  const filtered = useMemo(() => {
    if (!search) return buckets;
    const q = search.toLowerCase();
    return buckets.filter(b => b.label.toLowerCase().includes(q) || b.key.toLowerCase().includes(q));
  }, [buckets, search]);

  const sorted = useMemo(() => {
    return [...filtered].sort((a, b) => {
      const aActive = activeValues.has(a.key) ? 0 : 1;
      const bActive = activeValues.has(b.key) ? 0 : 1;
      if (aActive !== bActive) return aActive - bActive;
      return sortAsc ? a.count - b.count : b.count - a.count;
    });
  }, [filtered, activeValues, sortAsc]);

  const displayed = sorted.slice(0, visibleCount);
  const hasMore = sorted.length > visibleCount;

  const handleToggle = (value: string) => {
    const existing = allChips.find(c => c.field === field && c.operator === "eq" && c.value === value);
    if (existing) {
      removeChip(existing.id);
    } else {
      addChip({ field, operator: "eq", value });
      commitFilters();
    }
  };

  return (
    <div className="pb-2">
      {buckets.length > 5 && (
        <div className="mx-3 mb-1 flex items-center gap-1">
          <div className="relative flex-1 min-w-0">
            <MagnifyingGlassIcon className="absolute left-1.5 top-1/2 -translate-y-1/2 size-3 opacity-30" />
            <input
              type="text"
              value={search}
              onChange={e => setSearch(e.target.value)}
              placeholder="Filter values"
              className={twMerge(
                "w-full pl-5 pr-2 py-1 text-xs rounded",
                "bg-white dark:bg-dark-100",
                "border border-light-300 dark:border-dark-300",
                "placeholder:text-black/25 dark:placeholder:text-white/25",
                "focus:outline-none focus:border-brand-400 dark:focus:border-brand-500"
              )}
            />
          </div>
          <button
            type="button"
            onClick={() => setSortAsc(s => !s)}
            title={sortAsc ? "Sorted by count: lowest first" : "Sorted by count: highest first"}
            className={twMerge(
              "shrink-0 p-1 rounded cursor-pointer transition-colors",
              "border border-light-300 dark:border-dark-300",
              "text-black/40 dark:text-white/40 hover:text-black/70 dark:hover:text-white/70"
            )}
          >
            {sortAsc ? <BarsArrowUpIcon className="size-3.5" /> : <BarsArrowDownIcon className="size-3.5" />}
          </button>
        </div>
      )}

      {displayed.map(bucket => {
        const isActive = activeValues.has(bucket.key);
        const isExcluded = excludedValues.has(bucket.key);
        return (
          <button
            key={bucket.key}
            type="button"
            onClick={() => handleToggle(bucket.key)}
            className={twMerge(
              "w-full px-3 py-1 flex items-center gap-2 text-left text-sm cursor-pointer",
              "hover:bg-black/5 dark:hover:bg-white/5 transition-colors",
              isExcluded && "opacity-40 line-through"
            )}
          >
            <span
              className={twMerge(
                "flex items-center justify-center size-3.5 rounded-sm border shrink-0 transition-colors",
                isActive ? "bg-brand-500 border-brand-500 text-white" : "border-light-400 dark:border-dark-400"
              )}
            >
              {isActive && (
                <svg className="size-2.5" viewBox="0 0 10 10" fill="none" stroke="currentColor" strokeWidth="2">
                  <path d="M2 5l2.5 2.5L8 3" />
                </svg>
              )}
            </span>
            <span className="truncate flex-1 min-w-0">{bucket.label}</span>
            <span className="text-[11px] opacity-30 shrink-0 tabular-nums">{bucket.count.toLocaleString()}</span>
          </button>
        );
      })}

      {hasMore && (
        <button
          type="button"
          onClick={() => setVisibleCount(c => c + SHOW_MORE_STEP)}
          className="px-3 py-1 text-xs text-brand-600 dark:text-brand-400 cursor-pointer hover:underline"
        >
          Show more
        </button>
      )}

      {buckets.length === 0 && !isLoading && (
        <div className="px-3 py-1 text-xs text-black/25 dark:text-white/25">No values found</div>
      )}
    </div>
  );
};

// -------------------- Add Section Button --------------------

interface AddSectionButtonProps {
  sections: string[];
  onAdd: (field: string) => void;
  indexedAttrs: AttributeField[];
}

const AddSectionButton: React.FC<AddSectionButtonProps> = ({ sections, onAdd, indexedAttrs }) => {
  const [isOpen, setIsOpen] = useState(false);
  const [search, setSearch] = useState("");

  const sectionsSet = useMemo(() => new Set(sections), [sections]);

  const availableFields = useMemo(() => {
    const q = search.toLowerCase();
    const items: { key: string; label: string; category: string }[] = [];

    for (const f of SIDEBAR_ELIGIBLE_BUILTINS) {
      if (sectionsSet.has(f.key)) continue;
      if (q && !f.label.toLowerCase().includes(q) && !f.key.toLowerCase().includes(q)) continue;
      items.push({ key: f.key, label: f.label, category: f.category });
    }

    for (const attr of indexedAttrs) {
      const key = `attr:${attr.name}`;
      if (sectionsSet.has(key)) continue;
      if (q && !attr.name.toLowerCase().includes(q)) continue;
      items.push({ key, label: attr.name, category: "Attributes" });
    }

    return items;
  }, [sectionsSet, indexedAttrs, search]);

  if (!isOpen) {
    return (
      <button
        type="button"
        onClick={() => setIsOpen(true)}
        className="p-0.5 opacity-40 hover:opacity-100 cursor-pointer transition-opacity"
        title="Add filter section"
      >
        <PlusIcon className="size-4" />
      </button>
    );
  }

  return (
    <>
      {/* Backdrop */}
      <div
        className="fixed inset-0 z-40"
        onClick={() => {
          setIsOpen(false);
          setSearch("");
        }}
      />
      {/* Dropdown */}
      <div
        className={twMerge(
          "absolute z-50 top-8 left-2 right-2",
          "bg-white dark:bg-dark-100",
          "border border-light-300 dark:border-dark-300",
          "rounded-lg shadow-lg overflow-hidden"
        )}
      >
        <div className="p-2">
          <input
            type="text"
            value={search}
            onChange={e => setSearch(e.target.value)}
            placeholder="Search fields..."
            autoFocus
            className={twMerge(
              "w-full px-2 py-1.5 text-sm rounded",
              "border border-light-300 dark:border-dark-300",
              "bg-white dark:bg-dark-100",
              "placeholder:text-black/25 dark:placeholder:text-white/25",
              "focus:outline-none focus:border-brand-400"
            )}
          />
        </div>
        <div className="max-h-48 overflow-y-auto">
          {availableFields.length === 0 && (
            <div className="px-3 py-2 text-xs text-black/30 dark:text-white/30">No more fields to add</div>
          )}
          {availableFields.map(f => (
            <button
              key={f.key}
              type="button"
              onClick={() => {
                onAdd(f.key);
                setIsOpen(false);
                setSearch("");
              }}
              className="w-full px-3 py-1.5 text-left text-sm cursor-pointer hover:bg-black/5 dark:hover:bg-white/5 flex items-center gap-2"
            >
              <span className="truncate flex-1">{f.label}</span>
              <span className="text-[10px] text-black/30 dark:text-white/30 shrink-0">{f.category}</span>
            </button>
          ))}
        </div>
      </div>
    </>
  );
};
