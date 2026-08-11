import React from "react";
import { twMerge } from "tailwind-merge";
import { CheckIcon, AdjustmentsHorizontalIcon } from "@heroicons/react/20/solid";
import { DropdownSection, DropdownItem } from "./constants";
import { TypeBadge } from "./FilterChip";
import { Histogram } from "./Histogram";
import { DateRangePicker } from "./DateRangePicker";

interface FilterDropdownProps {
  sections: DropdownSection[];
  highlightedIndex: number;
  onItemClick: (item: DropdownItem) => void;
  onItemHover: (globalIndex: number) => void;
  dropdownRef: React.RefObject<HTMLDivElement | null>;
  inputRef: React.RefObject<HTMLInputElement | null>;
  checkedKeys?: Set<string>;
  histogram?: {
    bins: { key: number; doc_count: number }[];
    min: number;
    max: number;
    mode: "range" | "single";
    rangeStart: number | null;
    rangeEnd: number | null;
    onRangeChange: (start: number | null, end: number | null) => void;
    onApply: () => void;
  };
  /** Render inline (static position) instead of absolute overlay. Used inside dialogs. */
  positionStatic?: boolean;
  /** Show an Apply/Done button at the bottom of the dropdown. */
  onApply?: () => void;
  /** Label for the apply button. Defaults to "Apply". */
  applyLabel?: string;
  /** Total matching image count shown in the status bar. */
  totalCount?: number | null;
  /** Callback to open advanced filter dialog. If provided, shows the button in the status bar. */
  onAdvancedClick?: () => void;
  /** Whether advanced filter mode is currently active. */
  isAdvancedActive?: boolean;
  /** Date range picker props for date field filtering. */
  dateRange?: {
    startDate: string;
    endDate: string;
    onChange: (start: string, end: string) => void;
    onApply: () => void;
  };
  /** Additional CSS classes for the outer container. */
  className?: string;
  /** When provided, shows an "Only my queries" toggle (used in the stage-1 saved-queries picker). */
  savedQueriesFilter?: {
    onlyMine: boolean;
    onToggleMine: () => void;
  };
}

export const FilterDropdown: React.FC<FilterDropdownProps> = ({
  sections,
  highlightedIndex,
  onItemClick,
  onItemHover,
  dropdownRef,
  inputRef,
  checkedKeys,
  histogram,
  dateRange,
  positionStatic,
  onApply,
  totalCount,
  onAdvancedClick,
  isAdvancedActive,
  className: extraClassName,
  applyLabel = "Apply",
  savedQueriesFilter,
}) => (
  <div
    ref={dropdownRef}
    className={twMerge(
      positionStatic ? "relative" : "absolute z-50 left-0 right-0 mt-1",
      "bg-white dark:bg-dark-100",
      "border border-light-300 dark:border-dark-300",
      "rounded-lg shadow-lg overflow-hidden",
      "max-h-60 sm:max-h-80 overflow-y-auto",
      extraClassName
    )}
  >
    {/* Saved-queries "only mine" toggle (stage-1 picker only) */}
    {savedQueriesFilter && (
      <div className="flex items-center justify-end px-3 py-1.5 border-b border-light-200 dark:border-dark-300">
        <button
          type="button"
          onMouseDown={e => e.preventDefault()}
          onClick={savedQueriesFilter.onToggleMine}
          className={twMerge(
            "inline-flex items-center gap-1.5 text-[11px] cursor-pointer transition-colors",
            savedQueriesFilter.onlyMine
              ? "text-brand-700 dark:text-brand-300 font-medium"
              : "text-black/40 dark:text-white/40 hover:text-black/60 dark:hover:text-white/60"
          )}
        >
          <span
            className={twMerge(
              "flex items-center justify-center size-3.5 rounded border shrink-0",
              savedQueriesFilter.onlyMine
                ? "bg-brand-500 border-brand-500 text-white"
                : "border-light-400 dark:border-dark-400"
            )}
          >
            {savedQueriesFilter.onlyMine && <CheckIcon className="size-2.5" />}
          </span>
          Only my queries
        </button>
      </div>
    )}
    {/* Status bar: count + advanced search link */}
    {(totalCount != null || onAdvancedClick) && (
      <div className="sticky top-0 z-10 flex items-center justify-between px-3 py-1 bg-light dark:bg-dark-100 border-b border-light-300 dark:border-dark-300">
        {totalCount != null ? (
          <span className="text-[11px] tabular-nums text-black/40 dark:text-white/40">
            {totalCount.toLocaleString()} image{totalCount !== 1 ? "s" : ""} found
          </span>
        ) : (
          <span />
        )}
        {onAdvancedClick && (
          <button
            type="button"
            onMouseDown={e => e.preventDefault()}
            onClick={onAdvancedClick}
            className={twMerge(
              "inline-flex items-center gap-1 text-[11px] cursor-pointer transition-colors",
              isAdvancedActive
                ? "text-amber-700 dark:text-amber-400 font-medium"
                : "text-black/40 dark:text-white/40 hover:text-black/60 dark:hover:text-white/60"
            )}
          >
            <AdjustmentsHorizontalIcon className="size-3.5" />
            Advanced
          </button>
        )}
      </div>
    )}
    {/* Histogram mode for numeric fields */}
    {histogram && histogram.bins.length > 0 && (
      <>
        <div className="px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-black/30 dark:text-white/30 border-b border-light-200 dark:border-dark-300">
          Distribution
        </div>
        <Histogram {...histogram} />
      </>
    )}
    {/* Date range picker for date fields */}
    {dateRange && (
      <div className="px-2 py-2">
        <DateRangePicker startDate={dateRange.startDate} endDate={dateRange.endDate} onChange={dateRange.onChange} />
      </div>
    )}

    {sections.map(section => {
      if (section.items.length === 0) {
        return (
          <div key={section.header} className="px-3 py-2 text-xs text-black/40 dark:text-white/40">
            {section.header}
          </div>
        );
      }

      let globalOffset = 0;
      for (const s of sections) {
        if (s === section) break;
        globalOffset += s.items.length;
      }

      // Sort checked items to top when in multi-select mode
      const items = checkedKeys
        ? [...section.items].sort((a, b) => {
            const aChecked = checkedKeys.has(a.key) ? 0 : 1;
            const bChecked = checkedKeys.has(b.key) ? 0 : 1;
            return aChecked - bChecked;
          })
        : section.items;

      return (
        <div key={section.header}>
          <div className="px-3 py-1.5 text-[10px] font-semibold uppercase tracking-wider text-black/30 dark:text-white/30 border-b border-light-200 dark:border-dark-300">
            {section.header}
          </div>
          {items.map((item, localIdx) => {
            const globalIdx = globalOffset + localIdx;
            const isChecked = checkedKeys?.has(item.key);

            // "Show more" row: reveals the next page of values; no checkbox/count/badge.
            if (item.isShowMore) {
              return (
                <button
                  key={item.key}
                  type="button"
                  data-index={globalIdx}
                  className={twMerge(
                    "w-full px-3 py-1.5 text-left text-xs cursor-pointer text-brand-600 dark:text-brand-400",
                    "hover:bg-black/5 dark:hover:bg-white/5",
                    globalIdx === highlightedIndex && "bg-black/5 dark:bg-white/5"
                  )}
                  onMouseEnter={() => onItemHover(globalIdx)}
                  onMouseDown={e => e.preventDefault()}
                  onClick={() => {
                    onItemClick(item);
                    inputRef.current?.focus();
                  }}
                >
                  {item.label}
                </button>
              );
            }

            return (
              <button
                key={item.key}
                type="button"
                data-index={globalIdx}
                disabled={item.disabled}
                className={twMerge(
                  "w-full px-3 py-1.5 text-left text-sm flex items-center gap-2 cursor-pointer",
                  "hover:bg-black/5 dark:hover:bg-white/5",
                  globalIdx === highlightedIndex && "bg-black/5 dark:bg-white/5",
                  item.disabled && "opacity-40 cursor-not-allowed hover:bg-transparent dark:hover:bg-transparent"
                )}
                onMouseEnter={() => onItemHover(globalIdx)}
                onMouseDown={e => e.preventDefault()}
                onClick={() => {
                  onItemClick(item);
                  inputRef.current?.focus();
                }}
              >
                {/* Checkbox for multi-select */}
                {checkedKeys !== undefined && (
                  <span
                    className={twMerge(
                      "flex items-center justify-center size-4 rounded border shrink-0",
                      isChecked ? "bg-brand-500 border-brand-500 text-white" : "border-light-400 dark:border-dark-400"
                    )}
                  >
                    {isChecked && <CheckIcon className="size-3" />}
                  </span>
                )}
                {item.icon && <item.icon className="size-4 shrink-0 opacity-50" />}
                <span className="truncate flex-1 min-w-0">
                  <span className={item.emphasized ? "font-semibold" : undefined}>{item.label}</span>
                  {item.description && (
                    <span className="ml-2 text-xs text-black/30 dark:text-white/30 truncate">{item.description}</span>
                  )}
                </span>
                {item.rightLabel && (
                  <span className="text-xs text-black/40 dark:text-white/40 shrink-0">{item.rightLabel}</span>
                )}
                {item.typeBadge && <TypeBadge type={item.typeBadge} />}
                {item.count !== undefined && (
                  <span className="text-xs opacity-40 shrink-0 tabular-nums">{item.count.toLocaleString()}</span>
                )}
              </button>
            );
          })}
        </div>
      );
    })}

    {/* Apply button — visible when provided */}
    {onApply && (
      <div className="sticky bottom-0 border-t border-light-300 dark:border-dark-300 bg-white dark:bg-dark-100 px-3 py-2">
        <button
          type="button"
          onMouseDown={e => e.preventDefault()}
          onClick={onApply}
          className={twMerge(
            "w-full py-1.5 rounded-md text-sm font-medium cursor-pointer transition-colors",
            "bg-brand-600 text-white hover:bg-brand-700",
            "dark:bg-brand-500 dark:hover:bg-brand-600"
          )}
        >
          {applyLabel}
        </button>
      </div>
    )}
  </div>
);
