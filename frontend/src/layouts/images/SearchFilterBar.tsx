import React, { useEffect, useMemo, useRef, useState } from "react";
import ReactDOM from "react-dom";
import { twMerge } from "tailwind-merge";
import {
  XMarkIcon,
  MagnifyingGlassIcon,
  PhotoIcon,
  ChevronDownIcon,
  BookmarkIcon,
  TrashIcon,
  PencilSquareIcon,
  ArrowsPointingInIcon,
} from "@heroicons/react/20/solid";
import toast from "react-hot-toast";
import { useQueryClient } from "@tanstack/react-query";
import { ImageUploadField } from "../../components/forms/ImageUploadField";
import { ChipDisplay, CombinedNumericChipDisplay, GroupedChipDisplay, SimilarityChip } from "./filter/FilterChip";
import { FilterDropdown } from "./filter/FilterDropdown";
import {
  getFieldLabel,
  getOperatorSymbol,
  isMultiSelectField,
  BUILTIN_FIELDS,
  OPERATORS_BY_TYPE,
} from "./filter/constants";
import type { FieldType } from "./filter/constants";
import { NUMERIC_FIELDS, DATE_FIELDS } from "../../context/filterUtils";
import { useSearchFilterBar } from "./filter/useSearchFilterBar";
import { AdvancedFilterDialog } from "./filter/AdvancedFilterDialog";
import { SaveQueryDialog } from "./filter/SaveQueryDialog";
import type { FilterChip } from "../../context/ImageListDataContext";
import { useImageListData } from "../../context/ImageListDataContext";
import { useSettings } from "../../context/SettingsContext";
import { useQueriesList, useQueriesDestroy } from "../../api/client";

// Max chip groups shown inline in the bar before collapsing to "+N more"
const MAX_INLINE_CHIPS = 3;

type ChipGroup = {
  key: string;
  kind: "single" | "multi" | "numeric";
  field: string;
  operator: string;
  chips: FilterChip[];
};

function buildChipGroups(chips: FilterChip[]): ChipGroup[] {
  const groups: ChipGroup[] = [];
  const seen = new Map<string, number>();
  for (const chip of chips) {
    const isNumeric = NUMERIC_FIELDS.has(chip.field) || DATE_FIELDS.has(chip.field);
    const builtin = BUILTIN_FIELDS.find(f => f.key === chip.field);
    const isMulti = builtin
      ? isMultiSelectField(chip.field, builtin.fieldType)
      : chip.field.startsWith("attr:") && isMultiSelectField(chip.field, "enum");

    if (isNumeric && chip.operator !== "ne") {
      const groupKey = `numeric:${chip.field}`;
      const idx = seen.get(groupKey);
      if (idx !== undefined) {
        groups[idx].chips.push(chip);
      } else {
        seen.set(groupKey, groups.length);
        groups.push({ key: groupKey, kind: "numeric", field: chip.field, operator: chip.operator, chips: [chip] });
      }
    } else if (isMulti) {
      const groupKey = `multi:${chip.field}|${chip.operator}`;
      const idx = seen.get(groupKey);
      if (idx !== undefined) {
        groups[idx].chips.push(chip);
      } else {
        seen.set(groupKey, groups.length);
        groups.push({ key: groupKey, kind: "multi", field: chip.field, operator: chip.operator, chips: [chip] });
      }
    } else {
      groups.push({ key: chip.id, kind: "single", field: chip.field, operator: chip.operator, chips: [chip] });
    }
  }
  return groups;
}

function renderChipGroup(
  group: ChipGroup,
  handlers: {
    removeChip: (id: string) => void;
    removeChipGroup: (chips: FilterChip[]) => void;
    editChip: (chip: FilterChip) => void;
    editChipGroup: (field: string, operator: string) => void;
    editNumericField: (field: string) => void;
  }
) {
  if (group.kind === "numeric" && group.chips.length > 1) {
    return (
      <CombinedNumericChipDisplay
        key={group.key}
        chips={group.chips}
        onRemoveAll={() => handlers.removeChipGroup(group.chips)}
        onEdit={() => handlers.editNumericField(group.field)}
      />
    );
  }
  if (group.kind === "multi" && group.chips.length > 1) {
    return (
      <GroupedChipDisplay
        key={group.key}
        chips={group.chips}
        onRemoveAll={() => handlers.removeChipGroup(group.chips)}
        onEdit={() => handlers.editChipGroup(group.field, group.operator)}
      />
    );
  }
  return (
    <ChipDisplay
      key={group.chips[0].id}
      chip={group.chips[0]}
      onRemove={() => handlers.removeChip(group.chips[0].id)}
      onEdit={() => handlers.editChip(group.chips[0])}
    />
  );
}

// -------------------- Operator Switcher --------------------

const OperatorSwitcher: React.FC<{
  fieldType: FieldType;
  currentOp: string;
  onSelect: (op: string) => void;
}> = ({ fieldType, currentOp, onSelect }) => {
  const [open, setOpen] = useState(false);
  const btnRef = useRef<HTMLButtonElement>(null);
  const dropRef = useRef<HTMLDivElement>(null);
  const [pos, setPos] = useState<{ top: number; left: number }>({ top: 0, left: 0 });
  const ops = OPERATORS_BY_TYPE[fieldType] || [];

  // Position the portal dropdown below the button
  useEffect(() => {
    if (!open || !btnRef.current) return;
    const rect = btnRef.current.getBoundingClientRect();
    setPos({ top: rect.bottom + 2, left: rect.left });
  }, [open]);

  // Close on outside click
  useEffect(() => {
    if (!open) return;
    const handler = (e: MouseEvent) => {
      const t = e.target as Node;
      if (btnRef.current?.contains(t) || dropRef.current?.contains(t)) return;
      setOpen(false);
    };
    document.addEventListener("mousedown", handler);
    return () => document.removeEventListener("mousedown", handler);
  }, [open]);

  const current = ops.find(o => o.key === currentOp);

  return (
    <>
      <button
        ref={btnRef}
        type="button"
        onClick={e => {
          e.stopPropagation();
          setOpen(!open);
        }}
        className={twMerge(
          "inline-flex items-center gap-0.5 px-1 py-0.5 mx-0.5 rounded",
          "bg-brand-100 dark:bg-brand-900/50 text-brand-700 dark:text-brand-300",
          "hover:bg-brand-200 dark:hover:bg-brand-800 cursor-pointer transition-colors",
          "text-[11px] font-bold"
        )}
        title="Change operator"
      >
        {current?.symbol ?? getOperatorSymbol(currentOp)}
        <ChevronDownIcon className="size-2.5 opacity-60" />
      </button>
      {open &&
        ReactDOM.createPortal(
          <div
            ref={dropRef}
            data-filter-container
            style={{ position: "fixed", top: pos.top, left: pos.left, zIndex: 9999 }}
            className={twMerge(
              "bg-white dark:bg-dark-100",
              "border border-light-300 dark:border-dark-300",
              "rounded-lg shadow-lg overflow-hidden min-w-[8rem]"
            )}
          >
            {ops.map(op => (
              <button
                key={op.key}
                type="button"
                onClick={e => {
                  e.stopPropagation();
                  onSelect(op.key);
                  setOpen(false);
                }}
                className={twMerge(
                  "w-full px-2.5 py-1.5 text-left text-xs flex items-center gap-2 cursor-pointer",
                  "hover:bg-black/5 dark:hover:bg-white/5",
                  op.key === currentOp && "bg-brand-50 dark:bg-brand-900/30 font-bold"
                )}
              >
                <span className="w-4 text-center font-bold text-brand-600 dark:text-brand-400">{op.symbol}</span>
                <span className="opacity-70">{op.label}</span>
              </button>
            ))}
          </div>,
          document.body
        )}
    </>
  );
};

export const SearchFilterBar: React.FC = () => {
  const {
    totalCount,
    committedFilterParams,
    activeQuerySlug,
    queryCollapsed,
    clearActiveQuery,
    explodeQuery,
    collapseQuery,
  } = useImageListData();
  // A bound query shown as a compact pill: filters are hidden from the bar (and the URL) until the
  // user explodes it. Drives the suppression of the chips/input/clear UI below.
  const collapsed = queryCollapsed && !!activeQuerySlug;
  const { user } = useSettings();
  const [isSaveQueryOpen, setSaveQueryOpen] = useState(false);
  const hasCommittedFilters = Object.keys(committedFilterParams).length > 0;

  // Look up the active saved query (searching by slug, so it's found even with 100s of queries) to
  // decide whether the current user may update/delete it — the backend enforces author-only writes.
  const { data: queryList } = useQueriesList(
    { page_size: 100, search: activeQuerySlug ?? undefined },
    { query: { enabled: !!activeQuerySlug } }
  );
  const activeQuery = activeQuerySlug ? queryList?.results.find(q => q.slug === activeQuerySlug) : undefined;
  const isQueryOwner = !!activeQuery && activeQuery.author?.email === user.email;

  const queryClient = useQueryClient();
  const { mutate: destroyQuery, isPending: isDeleting } = useQueriesDestroy();
  const handleDeleteQuery = () => {
    if (!activeQuerySlug || !isQueryOwner) return;
    if (!window.confirm(`Delete saved query "${activeQuery?.name ?? activeQuerySlug}"? This cannot be undone.`)) return;
    destroyQuery(
      { slug: activeQuerySlug },
      {
        onSuccess: () => {
          toast.success("Query deleted");
          clearActiveQuery();
          queryClient.invalidateQueries({
            predicate: q =>
              Array.isArray(q.queryKey) && typeof q.queryKey[0] === "string" && q.queryKey[0].includes("/queries/"),
          });
        },
        onError: () => toast.error("Could not delete query"),
      }
    );
  };

  const hook = useSearchFilterBar();
  const {
    chips,
    inputValue,
    stage,
    onlyMine,
    setOnlyMine,
    isOpen,
    selectedField,
    selectedFieldType,
    selectedOperator,
    highlightedIndex,
    simMode,
    showImageUpload,
    isSimilarActive,
    simLabel,
    simValue,
    placeholder,
    dropdownSections,
    isMultiSelect,
    checkedKeys,
    histogramProps,
    isDateField,
    dateFrom,
    dateTo,
    setDateRange,
    commitDateRange,
    changeOperator,
    inputRef,
    containerRef,
    dropdownRef,
    setIsOpen,
    setShowImageUpload,
    setHighlightedIndex,
    handleInputChange,
    handleKeyDown,
    handleItemSelect,
    editChip,
    editChipGroup,
    editNumericField,
    removeChip,
    removeChipGroup,
    setModeBrowse,
    setModeSimilarFile,
    resetAutocomplete,
    handleDropdownApply,
    // lanes
    lanes,
    activeLaneId,
    setActiveLane,
    addLane,
    removeLane,
    toggleLaneNegated,
    clearAllLanes,
    isAdvancedFilter,
    // dialog
    isAdvancedDialogOpen,
    setAdvancedDialogOpen,
  } = hook;

  const allChips = useMemo(() => lanes.flatMap(l => l.chips), [lanes]);
  const hasFilters = allChips.length > 0;
  const chipGroups = useMemo(() => buildChipGroups(chips), [chips]);

  const chipHandlers = useMemo(
    () => ({ removeChip, removeChipGroup, editChip, editChipGroup, editNumericField }),
    [removeChip, removeChipGroup, editChip, editChipGroup, editNumericField]
  );

  const dateRangeProps = isDateField
    ? { startDate: dateFrom, endDate: dateTo, onChange: setDateRange, onApply: commitDateRange }
    : undefined;

  // When dialog is open, the input/dropdown live there, not here. While a query is collapsed the bar
  // shows only the pill, so the input (and the chips/clear UI below) are suppressed until it explodes.
  const showMainInput = !isAdvancedDialogOpen && !collapsed;
  // Whether the filter bar is "active" (focused/editing)
  const isBarActive = isOpen || !!selectedField || !!simMode;

  // Inline chips: show a few in the bar, rest as "+N more"
  const inlineGroups = chipGroups.slice(0, MAX_INLINE_CHIPS);
  const overflowCount = chipGroups.length - inlineGroups.length;

  return (
    <div ref={containerRef} data-filter-container className="relative flex-1 min-w-0 max-w-3xl">
      {/* Single-line bar */}
      <div
        className={twMerge(
          "flex flex-row items-center gap-1.5 px-2 rounded-lg border",
          "bg-white dark:bg-dark-100",
          "border-light-300 dark:border-dark-300",
          "focus-within:border-brand-400 dark:focus-within:border-brand-500",
          "h-[2.25rem] cursor-text overflow-hidden"
        )}
        onClick={() => {
          if (isAdvancedFilter) {
            setAdvancedDialogOpen(true);
          } else {
            inputRef.current?.focus();
            if (!simMode) setIsOpen(true);
          }
        }}
      >
        <MagnifyingGlassIcon className="size-4 opacity-40 shrink-0" />

        {/* Middle region: pills, chips and input. Kept in its own min-w-0 overflow-hidden flex box so
            many chips clip here instead of pushing the right-side buttons off the bar. mr keeps a gap
            before the action buttons when the content clips flush against the edge. */}
        <div className="flex flex-1 items-center gap-1.5 min-w-0 overflow-hidden mr-1.5">
          {/* Collapsed saved query: a compact pill. The name truncates with … while the bookmark and
            the edit/remove buttons stay pinned (shrink-0), so they never disappear for big queries. */}
          {collapsed ? (
            <div className="inline-flex items-center gap-1 min-w-0 flex-1 text-brand-700 dark:text-brand-300">
              <BookmarkIcon className="size-4 shrink-0" />
              <span
                className="truncate min-w-0 text-sm font-medium"
                title={activeQuery?.name ?? activeQuerySlug ?? undefined}
              >
                {activeQuery?.name ?? activeQuerySlug}
              </span>
              <button
                type="button"
                title="Edit this query's filters"
                onClick={e => {
                  e.stopPropagation();
                  explodeQuery();
                }}
                className="shrink-0 hover:opacity-100 opacity-60 cursor-pointer"
              >
                <PencilSquareIcon className="size-3.5" />
              </button>
              <button
                type="button"
                title="Remove this query"
                onClick={e => {
                  e.stopPropagation();
                  clearActiveQuery();
                }}
                className="shrink-0 hover:opacity-100 opacity-60 cursor-pointer"
              >
                <XMarkIcon className="size-3.5" />
              </button>
            </div>
          ) : (
            /* Exploded: the chips were loaded from this query and Save will overwrite it. The query is
             only a save-binding marker here (the chips do the filtering), so it's muted to read as
             passive — vs the collapsed pill above, which is the active filter and stays brand-colored. */
            activeQuerySlug && (
              <>
                <span
                  className="inline-flex items-center gap-1 text-sm font-medium text-black/50 dark:text-white/50 whitespace-nowrap shrink-0"
                  title={`You are editing the saved query "${activeQuerySlug}". Saving overwrites it; click ✕ to detach.`}
                >
                  <BookmarkIcon className="size-4" />
                  {activeQuerySlug}
                  <button
                    type="button"
                    title="Collapse this query"
                    onClick={e => {
                      e.stopPropagation();
                      collapseQuery();
                    }}
                    className="hover:opacity-100 opacity-60 cursor-pointer"
                  >
                    <ArrowsPointingInIcon className="size-3.5" />
                  </button>
                  <button
                    type="button"
                    title="Stop editing this query"
                    onClick={e => {
                      e.stopPropagation();
                      clearActiveQuery();
                    }}
                    className="hover:opacity-100 opacity-60 cursor-pointer"
                  >
                    <XMarkIcon className="size-3.5" />
                  </button>
                </span>
                {/* Divider separating the saved query from the filter chips it loaded. */}
                <span className="h-5 w-px bg-black/15 dark:bg-white/15 shrink-0" aria-hidden="true" />
              </>
            )
          )}

          {/* Active similarity chip */}
          {isSimilarActive && simLabel && (
            <SimilarityChip label={simLabel} value={simValue} onRemove={() => setModeBrowse()} />
          )}

          {/* Similarity input mode indicator */}
          {simMode && !isSimilarActive && (
            <span className="inline-flex items-center gap-0.5 text-xs text-amber-600 dark:text-amber-400 font-medium shrink-0">
              {simMode === "text" ? "Text search:" : "Vector:"}
              <button
                type="button"
                onClick={e => {
                  e.stopPropagation();
                  resetAutocomplete();
                }}
                className="hover:opacity-100 opacity-60 cursor-pointer"
              >
                <XMarkIcon className="size-3" />
              </button>
            </span>
          )}

          {/* Simple mode inline chips: desktop shows first few + overflow, mobile shows badge */}
          {!isAdvancedFilter && hasFilters && !isBarActive && !collapsed && (
            <>
              {/* Desktop: inline chips + "+N more" */}
              <span className="hidden sm:contents">
                {inlineGroups.map(g => renderChipGroup(g, chipHandlers))}
                {overflowCount > 0 && (
                  <span className="text-xs text-black/40 dark:text-white/40 whitespace-nowrap shrink-0">
                    +{overflowCount} more
                  </span>
                )}
              </span>
              {/* Mobile: compact badge */}
              <span className="sm:hidden text-xs text-brand-700 dark:text-brand-300 font-medium whitespace-nowrap">
                {allChips.length} filter{allChips.length !== 1 ? "s" : ""}
              </span>
            </>
          )}

          {/* Advanced mode: compact summary badge */}
          {isAdvancedFilter && !collapsed && (
            <span
              className={twMerge(
                "inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs whitespace-nowrap shrink-0 cursor-pointer",
                "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200",
                "hover:bg-amber-200 dark:hover:bg-amber-800 transition-colors"
              )}
              onClick={e => {
                e.stopPropagation();
                setAdvancedDialogOpen(true);
              }}
            >
              {lanes.length} group{lanes.length !== 1 ? "s" : ""}
              {allChips.length > 0 && (
                <span className="opacity-60">
                  ({allChips.length} filter{allChips.length !== 1 ? "s" : ""})
                </span>
              )}
            </span>
          )}

          {/* Selected field indicator */}
          {showMainInput && selectedField && (
            <span className="inline-flex items-center gap-0.5 text-xs text-brand-600 dark:text-brand-400 font-medium shrink-0">
              {getFieldLabel(selectedField)}
              {selectedOperator && selectedFieldType && (
                <OperatorSwitcher
                  fieldType={selectedFieldType}
                  currentOp={selectedOperator}
                  onSelect={changeOperator}
                />
              )}
              <button
                type="button"
                onClick={e => {
                  e.stopPropagation();
                  resetAutocomplete();
                }}
                className="hover:opacity-100 opacity-60 cursor-pointer"
              >
                <XMarkIcon className="size-3" />
              </button>
            </span>
          )}

          {/* Input */}
          {showMainInput && (
            <input
              ref={inputRef}
              type="text"
              autoComplete="off"
              name="filter-search"
              value={inputValue}
              onChange={handleInputChange}
              onFocus={() => {
                if (!simMode) setIsOpen(true);
              }}
              onKeyDown={handleKeyDown}
              placeholder={
                isAdvancedFilter ? "Edit filters..." : hasFilters && !isBarActive ? "Add filter..." : placeholder
              }
              className={twMerge(
                "flex-1 min-w-[4rem] sm:min-w-[8rem] text-sm bg-transparent border-none outline-none",
                "placeholder:text-black/30 dark:placeholder:text-white/30",
                "p-0 focus:ring-0"
              )}
            />
          )}

          {/* Spacer when input is hidden */}
          {!showMainInput && !collapsed && <div className="flex-1" />}
        </div>

        {/* Right side buttons */}
        <div className="flex items-center gap-1 shrink-0">
          {/* Similarity icon */}
          {!simMode && !isSimilarActive && allChips.length === 0 && (
            <button
              type="button"
              title="Similarity search"
              onClick={e => {
                e.stopPropagation();
                setShowImageUpload(true);
              }}
              className="opacity-30 hover:opacity-60 cursor-pointer shrink-0 transition-opacity"
            >
              <PhotoIcon className="size-4" />
            </button>
          )}

          {/* Save / update / delete the current filters as a saved query */}
          {hasCommittedFilters && !collapsed && (
            <>
              {activeQuerySlug ? (
                // Editing an existing query: only its author may overwrite it.
                <button
                  type="button"
                  disabled={!isQueryOwner}
                  title={
                    isQueryOwner
                      ? "Update this saved query with the current filters"
                      : "Only the author can update this query"
                  }
                  onClick={e => {
                    e.stopPropagation();
                    setSaveQueryOpen(true);
                  }}
                  className={twMerge(
                    "inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium shrink-0 transition-colors",
                    isQueryOwner
                      ? "cursor-pointer bg-brand-500/10 text-brand-700 hover:bg-brand-500/20 dark:bg-brand-400/15 dark:text-brand-300 dark:hover:bg-brand-400/25"
                      : "cursor-not-allowed opacity-40 bg-black/5 text-black/50 dark:bg-white/5 dark:text-white/50"
                  )}
                >
                  <BookmarkIcon className="size-4" />
                  Update
                </button>
              ) : (
                <button
                  type="button"
                  title="Save as query"
                  onClick={e => {
                    e.stopPropagation();
                    setSaveQueryOpen(true);
                  }}
                  className="inline-flex items-center gap-1 rounded-md px-2 py-1 text-xs font-medium cursor-pointer shrink-0 transition-colors bg-brand-500/10 text-brand-700 hover:bg-brand-500/20 dark:bg-brand-400/15 dark:text-brand-300 dark:hover:bg-brand-400/25"
                >
                  <BookmarkIcon className="size-4" />
                  Save
                </button>
              )}
              {activeQuerySlug && (
                <button
                  type="button"
                  disabled={!isQueryOwner || isDeleting}
                  title={isQueryOwner ? "Delete this saved query" : "Only the author can delete this query"}
                  onClick={e => {
                    e.stopPropagation();
                    handleDeleteQuery();
                  }}
                  className={twMerge(
                    "inline-flex items-center justify-center rounded-md p-1 shrink-0 transition-colors",
                    isQueryOwner
                      ? "cursor-pointer text-red-600 hover:bg-red-500/10 dark:text-red-400"
                      : "cursor-not-allowed opacity-40 text-black/40 dark:text-white/40"
                  )}
                >
                  <TrashIcon className="size-4" />
                </button>
              )}
            </>
          )}

          {/* Clear all */}
          {(hasFilters || isSimilarActive) && !collapsed && (
            <button
              type="button"
              onClick={e => {
                e.stopPropagation();
                clearAllLanes();
                if (isSimilarActive) setModeBrowse();
                resetAutocomplete();
              }}
              className="opacity-40 hover:opacity-100 cursor-pointer shrink-0"
            >
              <XMarkIcon className="size-4" />
            </button>
          )}
        </div>
      </div>

      {isSaveQueryOpen && (
        <SaveQueryDialog
          filters={committedFilterParams}
          boundSlug={activeQuerySlug}
          onClose={() => setSaveQueryOpen(false)}
        />
      )}

      {/* Combined overlay: chips panel + dropdown stacked together */}
      {showMainInput && isBarActive && !simMode && !isAdvancedFilter && (
        <div className="absolute z-50 left-0 right-0 mt-1">
          {/* Chips panel */}
          {chipGroups.length > 0 && (
            <div
              className={twMerge(
                "bg-white dark:bg-dark-100",
                "border border-light-300 dark:border-dark-300",
                isOpen && (dropdownSections.length > 0 || histogramProps)
                  ? "rounded-t-lg border-b-0"
                  : "rounded-lg shadow-lg",
                "p-2 flex flex-wrap gap-1"
              )}
            >
              {chipGroups.map(g => renderChipGroup(g, chipHandlers))}
            </div>
          )}
          {/* Dropdown (directly below chips, shares the same overlay) */}
          {isOpen && (dropdownSections.length > 0 || histogramProps || dateRangeProps) && (
            <FilterDropdown
              sections={dropdownSections}
              highlightedIndex={highlightedIndex}
              onItemClick={item => {
                handleItemSelect(item);
                inputRef.current?.focus();
              }}
              onItemHover={setHighlightedIndex}
              dropdownRef={dropdownRef}
              inputRef={inputRef}
              checkedKeys={isMultiSelect ? checkedKeys : undefined}
              histogram={histogramProps}
              dateRange={dateRangeProps}
              onApply={handleDropdownApply}
              applyLabel={selectedField ? "Apply" : "Done"}
              totalCount={totalCount}
              onAdvancedClick={() => setAdvancedDialogOpen(true)}
              isAdvancedActive={isAdvancedFilter}
              positionStatic
              className={chipGroups.length > 0 ? "rounded-t-none border-t-0" : undefined}
              savedQueriesFilter={
                stage === 1 && !simMode ? { onlyMine, onToggleMine: () => setOnlyMine(v => !v) } : undefined
              }
            />
          )}
        </div>
      )}

      {/* Advanced filter dialog */}
      {isAdvancedDialogOpen && (
        <AdvancedFilterDialog
          lanes={lanes}
          activeLaneId={activeLaneId}
          onSetActiveLane={setActiveLane}
          onAddLane={addLane}
          onRemoveLane={removeLane}
          onToggleNegated={toggleLaneNegated}
          onClose={() => setAdvancedDialogOpen(false)}
          totalCount={totalCount}
          inputValue={inputValue}
          selectedField={selectedField}
          selectedOperator={selectedOperator}
          isOpen={isOpen}
          highlightedIndex={highlightedIndex}
          placeholder={placeholder}
          dropdownSections={dropdownSections}
          isMultiSelect={isMultiSelect}
          checkedKeys={checkedKeys}
          histogramProps={histogramProps}
          inputRef={inputRef}
          dropdownRef={dropdownRef}
          setIsOpen={setIsOpen}
          setHighlightedIndex={setHighlightedIndex}
          handleInputChange={handleInputChange}
          handleKeyDown={handleKeyDown}
          handleItemSelect={handleItemSelect}
          editChip={editChip}
          editChipGroup={editChipGroup}
          editNumericField={editNumericField}
          removeChip={removeChip}
          removeChipGroup={removeChipGroup}
          resetAutocomplete={resetAutocomplete}
          handleDropdownApply={handleDropdownApply}
        />
      )}

      {/* Image upload overlay */}
      {showImageUpload && (
        <div
          className={twMerge(
            "absolute z-50 left-0 right-0 mt-1",
            "bg-white dark:bg-dark-100",
            "border border-light-300 dark:border-dark-300",
            "rounded-lg shadow-lg p-3"
          )}
        >
          <div className="flex items-center justify-between mb-2">
            <span className="text-xs font-medium opacity-60">Upload image for similarity search</span>
            <button
              type="button"
              onClick={() => setShowImageUpload(false)}
              className="opacity-40 hover:opacity-100 cursor-pointer"
            >
              <XMarkIcon className="size-4" />
            </button>
          </div>
          <ImageUploadField
            onUpload={file => {
              clearAllLanes();
              setModeSimilarFile(file);
              setShowImageUpload(false);
              resetAutocomplete();
            }}
          />
        </div>
      )}

      {/* Dropdown for similarity mode (no chips/overlay) */}
      {showMainInput && isOpen && simMode && (dropdownSections.length > 0 || histogramProps) && (
        <FilterDropdown
          sections={dropdownSections}
          highlightedIndex={highlightedIndex}
          onItemClick={item => {
            handleItemSelect(item);
            inputRef.current?.focus();
          }}
          onItemHover={setHighlightedIndex}
          dropdownRef={dropdownRef}
          inputRef={inputRef}
        />
      )}
    </div>
  );
};
