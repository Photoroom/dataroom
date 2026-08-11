import React, { useEffect, useMemo } from "react";
import ReactDOM from "react-dom";
import { twMerge } from "tailwind-merge";
import { XMarkIcon, PlusIcon, MagnifyingGlassIcon, NoSymbolIcon } from "@heroicons/react/20/solid";
import { ChipDisplay, CombinedNumericChipDisplay, GroupedChipDisplay } from "./FilterChip";
import { FilterDropdown } from "./FilterDropdown";
import { getFieldLabel, getOperatorSymbol, isMultiSelectField, BUILTIN_FIELDS } from "./constants";
import { NUMERIC_FIELDS } from "../../../context/filterUtils";
import type { FilterChip as FilterChipType, FilterLane } from "../../../context/ImageListDataContext";
import type { DropdownSection } from "./constants";

// -------------------- Types --------------------

interface AdvancedFilterDialogProps {
  lanes: FilterLane[];
  activeLaneId: string;
  onSetActiveLane: (id: string) => void;
  onAddLane: () => void;
  onRemoveLane: (id: string) => void;
  onToggleNegated: (id: string) => void;
  onClose: () => void;
  totalCount: number | null;
  // Active group filter editing (from useSearchFilterBar)
  inputValue: string;
  selectedField: string | null;
  selectedOperator: string | null;
  isOpen: boolean;
  highlightedIndex: number;
  placeholder: string;
  dropdownSections: DropdownSection[];
  isMultiSelect: boolean;
  checkedKeys: Set<string>;
  histogramProps?: {
    bins: { key: number; doc_count: number }[];
    min: number;
    max: number;
    mode: "range" | "single";
    rangeStart: number | null;
    rangeEnd: number | null;
    onRangeChange: (start: number | null, end: number | null) => void;
    onApply: () => void;
  };
  inputRef: React.RefObject<HTMLInputElement | null>;
  dropdownRef: React.RefObject<HTMLDivElement | null>;
  setIsOpen: (open: boolean) => void;
  setHighlightedIndex: (index: number) => void;
  handleInputChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  handleKeyDown: (e: React.KeyboardEvent) => void;
  handleItemSelect: (item: { key: string; disabled?: boolean }) => void;
  editChip: (chip: FilterChipType) => void;
  editChipGroup: (field: string, operator: string) => void;
  editNumericField: (field: string) => void;
  removeChip: (id: string) => void;
  removeChipGroup: (chips: FilterChipType[]) => void;
  resetAutocomplete: () => void;
  handleDropdownApply: () => void;
}

// -------------------- Chip grouping --------------------

function chipGroupsForLane(chips: FilterChipType[]) {
  type ChipGroup = {
    key: string;
    kind: "single" | "multi" | "numeric";
    field: string;
    operator: string;
    chips: FilterChipType[];
  };
  const groups: ChipGroup[] = [];
  const seen = new Map<string, number>();
  for (const chip of chips) {
    const isNumeric = NUMERIC_FIELDS.has(chip.field);
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

// -------------------- Dialog --------------------

export const AdvancedFilterDialog: React.FC<AdvancedFilterDialogProps> = props => {
  const {
    lanes,
    activeLaneId,
    onSetActiveLane,
    onAddLane,
    onRemoveLane,
    onToggleNegated,
    onClose,
    totalCount,
    inputValue,
    selectedField,
    selectedOperator,
    isOpen,
    highlightedIndex,
    placeholder,
    dropdownSections,
    isMultiSelect,
    checkedKeys,
    histogramProps,
    inputRef,
    dropdownRef,
    setIsOpen,
    setHighlightedIndex,
    handleInputChange,
    handleKeyDown,
    handleItemSelect,
    editChip,
    editChipGroup,
    editNumericField,
    removeChip,
    removeChipGroup,
    resetAutocomplete,
    handleDropdownApply,
  } = props;

  const activeLane = lanes.find(l => l.id === activeLaneId);
  const canAddGroup = activeLane ? activeLane.chips.length > 0 : false;

  // Focus the input when dialog opens
  useEffect(() => {
    setTimeout(() => inputRef.current?.focus(), 50);
  }, [inputRef]);

  // ESC: close active filter box first, only close dialog when nothing is active
  useEffect(() => {
    const handleEsc = (e: KeyboardEvent) => {
      // Only handle ESC that wasn't already handled by the input's onKeyDown
      // The input's handleKeyDown handles ESC for field/operator/histogram states.
      // This handler catches ESC when the input has no active state (stage 1, nothing open).
      if (e.key === "Escape" && !selectedField && !isOpen) {
        // Close the dialog only when the active box has no dropdown open
        onClose();
      }
    };
    document.addEventListener("keydown", handleEsc);
    return () => document.removeEventListener("keydown", handleEsc);
  }, [onClose, selectedField, isOpen]);

  // Click on a chip in a non-active box: switch to that box and edit
  const handleCrossBoxEditChip = (chip: FilterChipType, laneId: string) => {
    if (laneId !== activeLaneId) {
      resetAutocomplete();
      onSetActiveLane(laneId);
      // editChip will be called after the lane switch (via useEffect + setTimeout)
      setTimeout(() => editChip(chip), 100);
    } else {
      editChip(chip);
    }
  };

  const handleCrossBoxEditChipGroup = (field: string, operator: string, laneId: string) => {
    if (laneId !== activeLaneId) {
      resetAutocomplete();
      onSetActiveLane(laneId);
      setTimeout(() => editChipGroup(field, operator), 100);
    } else {
      editChipGroup(field, operator);
    }
  };

  const handleCrossBoxEditNumeric = (field: string, laneId: string) => {
    if (laneId !== activeLaneId) {
      resetAutocomplete();
      onSetActiveLane(laneId);
      setTimeout(() => editNumericField(field), 100);
    } else {
      editNumericField(field);
    }
  };

  return ReactDOM.createPortal(
    <div
      className={twMerge(
        "fixed z-40 top-0 left-0 right-0 bottom-0 w-full h-full",
        "flex justify-center items-start sm:items-center",
        "bg-black/50"
      )}
      onMouseDown={e => {
        // Close when clicking backdrop
        if (e.target === e.currentTarget) {
          resetAutocomplete();
          onClose();
        }
      }}
    >
      <div
        className={twMerge(
          "w-full max-w-2xl max-h-[85vh] overflow-auto",
          "bg-light-100 dark:bg-dark rounded-2xl",
          "m-0 sm:m-4 p-5 sm:p-6",
          // Mobile: full-width bottom sheet
          "fixed bottom-0 sm:relative sm:bottom-auto"
        )}
      >
        {/* Header */}
        <div className="flex items-center justify-between mb-4">
          <div className="flex items-center gap-3">
            <h3 className="text-sm font-semibold">Advanced Filters</h3>
            {totalCount !== null && (
              <span className="text-[11px] tabular-nums text-black/40 dark:text-white/40">
                {totalCount.toLocaleString()} image{totalCount !== 1 ? "s" : ""} found
              </span>
            )}
          </div>
          <button
            type="button"
            onClick={() => {
              resetAutocomplete();
              onClose();
            }}
            className="opacity-40 hover:opacity-100 cursor-pointer transition-opacity"
          >
            <XMarkIcon className="size-5" />
          </button>
        </div>

        {/* Filter groups */}
        <div className="flex flex-col gap-3">
          {lanes.map((lane, idx) => (
            <React.Fragment key={lane.id}>
              {idx > 0 && (
                <div className="flex items-center gap-3 px-1">
                  <div className="flex-1 border-t border-light-300 dark:border-dark-300" />
                  <span className="text-xs font-semibold uppercase tracking-wider text-amber-600 dark:text-amber-400">
                    OR
                  </span>
                  <div className="flex-1 border-t border-light-300 dark:border-dark-300" />
                </div>
              )}
              <FilterGroupBox
                lane={lane}
                isActive={lane.id === activeLaneId}
                canRemove={lanes.length > 1}
                onActivate={() => {
                  if (lane.id !== activeLaneId) {
                    resetAutocomplete();
                    onSetActiveLane(lane.id);
                  }
                }}
                onRemove={() => onRemoveLane(lane.id)}
                onToggleNegated={() => onToggleNegated(lane.id)}
                // Active group filter editing props
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
                onEditChip={handleCrossBoxEditChip}
                onEditChipGroup={handleCrossBoxEditChipGroup}
                onEditNumericField={handleCrossBoxEditNumeric}
                removeChip={removeChip}
                removeChipGroup={removeChipGroup}
                handleDropdownApply={handleDropdownApply}
              />
            </React.Fragment>
          ))}
        </div>

        {/* Add group button */}
        <button
          type="button"
          onClick={() => {
            if (canAddGroup) {
              resetAutocomplete();
              onAddLane();
            }
          }}
          disabled={!canAddGroup}
          className={twMerge(
            "flex items-center gap-1.5 mt-3 px-3 py-2 text-xs rounded-lg transition-colors",
            canAddGroup
              ? "text-brand-600 dark:text-brand-400 hover:bg-black/5 dark:hover:bg-white/5 cursor-pointer"
              : "text-black/20 dark:text-white/20 cursor-not-allowed"
          )}
        >
          <PlusIcon className="size-4" />
          Add OR group
        </button>
      </div>
    </div>,
    document.body
  );
};

// -------------------- Filter Group Box --------------------

const FilterGroupBox: React.FC<{
  lane: FilterLane;
  isActive: boolean;
  canRemove: boolean;
  onActivate: () => void;
  onRemove: () => void;
  onToggleNegated: () => void;
  // Active group filter editing props (only used when isActive)
  inputValue: string;
  selectedField: string | null;
  selectedOperator: string | null;
  isOpen: boolean;
  highlightedIndex: number;
  placeholder: string;
  dropdownSections: DropdownSection[];
  isMultiSelect: boolean;
  checkedKeys: Set<string>;
  histogramProps?: {
    bins: { key: number; doc_count: number }[];
    min: number;
    max: number;
    mode: "range" | "single";
    rangeStart: number | null;
    rangeEnd: number | null;
    onRangeChange: (start: number | null, end: number | null) => void;
    onApply: () => void;
  };
  inputRef: React.RefObject<HTMLInputElement | null>;
  dropdownRef: React.RefObject<HTMLDivElement | null>;
  setIsOpen: (open: boolean) => void;
  setHighlightedIndex: (index: number) => void;
  handleInputChange: (e: React.ChangeEvent<HTMLInputElement>) => void;
  handleKeyDown: (e: React.KeyboardEvent) => void;
  handleItemSelect: (item: { key: string; disabled?: boolean }) => void;
  onEditChip: (chip: FilterChipType, laneId: string) => void;
  onEditChipGroup: (field: string, operator: string, laneId: string) => void;
  onEditNumericField: (field: string, laneId: string) => void;
  removeChip: (id: string) => void;
  removeChipGroup: (chips: FilterChipType[]) => void;
  handleDropdownApply: () => void;
}> = ({
  lane,
  isActive,
  canRemove,
  onActivate,
  onRemove,
  onToggleNegated,
  inputValue,
  selectedField,
  selectedOperator,
  isOpen,
  highlightedIndex,
  placeholder,
  dropdownSections,
  isMultiSelect,
  checkedKeys,
  histogramProps,
  inputRef,
  dropdownRef,
  setIsOpen,
  setHighlightedIndex,
  handleInputChange,
  handleKeyDown,
  handleItemSelect,
  onEditChip,
  onEditChipGroup,
  onEditNumericField,
  removeChip,
  removeChipGroup,
  handleDropdownApply,
}) => {
  const groups = useMemo(() => chipGroupsForLane(lane.chips), [lane.chips]);

  return (
    <div
      data-filter-container
      className={twMerge(
        "relative rounded-lg border transition-colors",
        lane.negated && "ring-1 ring-red-300 dark:ring-red-800",
        isActive
          ? "border-brand-400 dark:border-brand-600 bg-white dark:bg-dark-100"
          : "border-light-300 dark:border-dark-300 bg-white dark:bg-dark-100 cursor-pointer hover:border-black/20 dark:hover:border-white/20"
      )}
      onClick={() => {
        if (!isActive) onActivate();
      }}
    >
      {/* Header row: negate toggle + label + delete */}
      <div className="flex items-center gap-2 px-3 py-1.5">
        <span className="flex-1 text-xs text-black/40 dark:text-white/40">
          {lane.negated ? "Include images that do NOT match:" : "Include images where:"}
        </span>
        <button
          type="button"
          onClick={e => {
            e.stopPropagation();
            onToggleNegated();
          }}
          className={twMerge(
            "inline-flex items-center gap-1 text-[11px] px-2 py-0.5 rounded-full cursor-pointer transition-all",
            lane.negated
              ? "bg-red-100 text-red-700 dark:bg-red-500/20 dark:text-red-400 font-medium"
              : "text-black/25 dark:text-white/25 hover:text-black/50 dark:hover:text-white/50 hover:bg-black/5 dark:hover:bg-white/5"
          )}
          title={
            lane.negated
              ? "Negated: includes complement. Click to match normally."
              : "Click to negate (include complement)"
          }
        >
          <NoSymbolIcon className={twMerge("size-3", lane.negated ? "opacity-100" : "opacity-50")} />
          Negate
        </button>
        {canRemove && (
          <button
            type="button"
            onClick={e => {
              e.stopPropagation();
              onRemove();
            }}
            className="text-black/25 dark:text-white/25 hover:text-black/60 dark:hover:text-white/60 cursor-pointer transition-colors"
            title="Remove group"
          >
            <XMarkIcon className="size-4" />
          </button>
        )}
      </div>

      {/* Filter content */}
      <div className="px-3 pb-3">
        {isActive ? (
          // Active group: full filter bar experience
          <div>
            <div
              className={twMerge(
                "flex flex-row items-center gap-1.5 px-2 py-1 rounded-lg border",
                "bg-black/[0.02] dark:bg-white/[0.03]",
                "border-light-300 dark:border-dark-300",
                "focus-within:border-brand-400 dark:focus-within:border-brand-500",
                "min-h-[2.25rem] flex-wrap cursor-text"
              )}
              onClick={() => {
                inputRef.current?.focus();
                setIsOpen(true);
              }}
            >
              <MagnifyingGlassIcon className="size-4 opacity-40 shrink-0" />

              {/* Chips */}
              {groups.map(group =>
                group.kind === "numeric" && group.chips.length > 1 ? (
                  <CombinedNumericChipDisplay
                    key={group.key}
                    chips={group.chips}
                    onRemoveAll={() => removeChipGroup(group.chips)}
                    onEdit={() => onEditNumericField(group.field, lane.id)}
                  />
                ) : group.kind === "multi" && group.chips.length > 1 ? (
                  <GroupedChipDisplay
                    key={group.key}
                    chips={group.chips}
                    onRemoveAll={() => removeChipGroup(group.chips)}
                    onEdit={() => onEditChipGroup(group.field, group.operator, lane.id)}
                  />
                ) : (
                  <ChipDisplay
                    key={group.chips[0].id}
                    chip={group.chips[0]}
                    onRemove={() => removeChip(group.chips[0].id)}
                    onEdit={() => onEditChip(group.chips[0], lane.id)}
                  />
                )
              )}

              {/* Selected field indicator */}
              {selectedField && (
                <span className="inline-flex items-center gap-0.5 text-xs text-brand-600 dark:text-brand-400 font-medium shrink-0">
                  {getFieldLabel(selectedField)}
                  {selectedOperator && (
                    <span className="text-brand-500 dark:text-brand-300 mx-0.5">
                      {getOperatorSymbol(selectedOperator)}
                    </span>
                  )}
                </span>
              )}

              {/* Input */}
              <input
                ref={inputRef}
                type="text"
                autoComplete="off"
                name="dialog-filter-search"
                value={inputValue}
                onChange={handleInputChange}
                onFocus={() => setIsOpen(true)}
                onKeyDown={handleKeyDown}
                placeholder={groups.length > 0 ? "Add filter..." : placeholder}
                className={twMerge(
                  "flex-1 min-w-[6rem] text-sm bg-transparent border-none outline-none",
                  "placeholder:text-black/30 dark:placeholder:text-white/30",
                  "p-0 focus:ring-0"
                )}
              />
            </div>

            {/* Dropdown */}
            {isOpen && (dropdownSections.length > 0 || histogramProps) && (
              <div className="mt-1">
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
                  positionStatic
                  onApply={handleDropdownApply}
                  applyLabel={selectedField ? "Apply" : "Done"}
                />
              </div>
            )}
          </div>
        ) : (
          // Inactive group: chips display only (clicking edits cross-box)
          <div className="flex flex-wrap gap-1 min-h-[1.75rem] items-center">
            {groups.length === 0 ? (
              <span className="text-xs text-black/30 dark:text-white/30 italic">Click to add filters...</span>
            ) : (
              groups.map(group =>
                group.kind === "numeric" && group.chips.length > 1 ? (
                  <CombinedNumericChipDisplay
                    key={group.key}
                    chips={group.chips}
                    onRemoveAll={() => removeChipGroup(group.chips)}
                    onEdit={() => onEditNumericField(group.field, lane.id)}
                  />
                ) : group.kind === "multi" && group.chips.length > 1 ? (
                  <GroupedChipDisplay
                    key={group.key}
                    chips={group.chips}
                    onRemoveAll={() => removeChipGroup(group.chips)}
                    onEdit={() => onEditChipGroup(group.field, group.operator, lane.id)}
                  />
                ) : (
                  <ChipDisplay
                    key={group.chips[0].id}
                    chip={group.chips[0]}
                    onRemove={() => removeChip(group.chips[0].id)}
                    onEdit={() => onEditChip(group.chips[0], lane.id)}
                  />
                )
              )
            )}
          </div>
        )}
      </div>
    </div>
  );
};
