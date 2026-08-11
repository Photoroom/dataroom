import React, { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  useGroupsList,
  useGroupTypesList,
  useQueriesList,
  useRolesList,
  useStatsAttributesList,
  useStatsLatentTypesList,
} from "../../../api/client";
import { FilterChip, ImageListMode, useImageListData } from "../../../context/ImageListDataContext";
import { useSettings } from "../../../context/SettingsContext";
import { PhotoIcon, ArrowsRightLeftIcon, DocumentTextIcon } from "@heroicons/react/20/solid";
import {
  FieldType,
  BUILTIN_FIELDS,
  OPERATOR_SHORTCUTS,
  SHOW_MORE_KEY,
  getAttrFieldType,
  isCatalogField,
  isMultiSelectField,
} from "./constants";
import { getNumericConflicts, parseDateRangeInput } from "./numericConflicts";
import { useFacets } from "./useFacets";
import { overlayFacetCounts, useFieldCatalog, usePrefetchCommonCatalogs } from "./useFieldCatalog";
import { useNumericHistogram } from "./useNumericHistogram";
import { useDropdownSections } from "./useDropdownSections";

// Stage-3 value list pagination: show this many, then "Show more" reveals +STEP each click.
const VALUE_PAGE_SIZE = 10;
const VALUE_PAGE_STEP = 50;

const SIMILARITY_ICONS: Record<string, React.ComponentType<{ className?: string }>> = {
  DocumentTextIcon,
  PhotoIcon,
  ArrowsRightLeftIcon,
};

export function useSearchFilterBar() {
  const {
    chips,
    addChip,
    removeChip,
    clearChips,
    removeChipDraft,
    mode,
    setModeBrowse,
    setModeSimilarText,
    setModeSimilarFile,
    setModeSimilarVector,
    similarImage,
    similarText,
    similarFile,
    similarVector,
    lanes,
    activeLaneId,
    setActiveLane,
    addLane,
    removeLane,
    toggleLaneNegated,
    clearAllLanes,
    isAdvancedFilter,
    commitFilters,
    collapseToQuery,
    activeQuerySlug,
  } = useImageListData();
  const { user } = useSettings();

  // ---- Autocomplete state ----
  const [inputValue, setInputValue] = useState("");
  const [isOpen, setIsOpen] = useState(false);
  const [selectedField, setSelectedField] = useState<string | null>(null);
  const [selectedFieldType, setSelectedFieldType] = useState<FieldType | null>(null);
  const [selectedOperator, setSelectedOperator] = useState<string | null>(null);
  const [highlightedIndex, setHighlightedIndex] = useState(0);

  // ---- Date range picker state ----
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");

  // ---- Similarity state ----
  const [simMode, setSimMode] = useState<"text" | "image" | "vector" | null>(null);
  const [showImageUpload, setShowImageUpload] = useState(false);

  // ---- Advanced dialog state ----
  const [isAdvancedDialogOpen, setAdvancedDialogOpen] = useState(false);

  const inputRef = useRef<HTMLInputElement>(null);
  const containerRef = useRef<HTMLDivElement>(null);
  const dropdownRef = useRef<HTMLDivElement>(null);

  // ---- Derived state ----
  // "Only mine" toggle for the saved-queries list (stage 1). Restricts the fetch to ?mine=true.
  const [onlyMine, setOnlyMine] = useState(false);

  const stage: 1 | 2 | 3 = selectedField ? (selectedOperator ? 3 : 2) : 1;
  const isSimilarActive = mode === ImageListMode.SIMILAR;
  const isNumericField = selectedFieldType === "numeric";
  const isDateField = selectedFieldType === "date";
  const isRangeOp = selectedOperator === "range";
  const isSingleNumericOp = isNumericField && stage === 3 && !isRangeOp && selectedOperator !== "ne";

  const isMultiSelect = useMemo(
    () =>
      stage === 3 &&
      selectedField !== null &&
      selectedFieldType !== null &&
      isMultiSelectField(selectedField, selectedFieldType),
    [stage, selectedField, selectedFieldType]
  );

  const checkedKeys = useMemo((): Set<string> => {
    if (!isMultiSelect || !selectedField || !selectedOperator) return new Set();
    return new Set(chips.filter(c => c.field === selectedField && c.operator === selectedOperator).map(c => c.value));
  }, [isMultiSelect, selectedField, selectedOperator, chips]);

  // ---- Reset ----
  // Light reset: clears field/operator/input only (not similarity state).
  // Used when switching lanes so sim mode survives clearAllLanes().
  const resetFilterState = useCallback(() => {
    setSelectedField(null);
    setSelectedFieldType(null);
    setSelectedOperator(null);
    setInputValue("");
    setDateFrom("");
    setDateTo("");
    setHighlightedIndex(0);
  }, []);

  // Full reset: clears everything including similarity state, commits draft filters.
  const resetAutocomplete = useCallback(() => {
    resetFilterState();
    setSimMode(null);
    setShowImageUpload(false);
    commitFilters();
  }, [resetFilterState, commitFilters]);

  // Reset filter state (not sim) when active lane changes (user switched groups)
  useEffect(() => {
    resetFilterState();
    setIsOpen(false);
  }, [activeLaneId, resetFilterState]);

  // Unbounded fields (source, tag, dataset, keyword attrs) list values from the cached
  // catalog. Facets are still fetched for them while filters on OTHER fields are active,
  // to overlay filter-aware counts on that list (the catalog's own counts are global).
  const isCatalogSelected = useMemo(
    () => (selectedField ? isCatalogField(selectedField, selectedFieldType ?? undefined) : false),
    [selectedField, selectedFieldType]
  );
  const hasOtherFilters = useMemo(
    () => !!selectedField && chips.some(c => c.field !== selectedField),
    [chips, selectedField]
  );

  // Stage-3 value list pagination (reset whenever the working set changes).
  const [valueLimit, setValueLimit] = useState(VALUE_PAGE_SIZE);
  useEffect(() => {
    setValueLimit(VALUE_PAGE_SIZE);
  }, [selectedField, selectedOperator, inputValue]);
  const showMoreValues = useCallback(() => setValueLimit(n => n + VALUE_PAGE_STEP), []);

  // Warm the common catalogs on mount so the value list is instant when the user reaches stage 3.
  usePrefetchCommonCatalogs();

  // ---- Data fetching ----
  const { data: attributesData } = useStatsAttributesList();
  const {
    buckets: facetBuckets,
    stats: facetStats,
    histogram: facetHistogram,
    isLoading: facetsLoading,
  } = useFacets(chips, selectedField, stage === 3 && (!isCatalogSelected || hasOtherFilters));
  const { values: catalogValues } = useFieldCatalog(stage === 3 ? selectedField : null, selectedFieldType ?? undefined);

  // Catalog list with filter-aware counts overlaid once the facets for the active filters
  // have loaded (until then — and with no other filters active — show the global counts).
  const effectiveCatalogValues = useMemo(() => {
    if (!isCatalogSelected || !hasOtherFilters || facetsLoading) return catalogValues;
    return overlayFacetCounts(catalogValues, facetBuckets);
  }, [isCatalogSelected, hasOtherFilters, facetsLoading, catalogValues, facetBuckets]);
  const { data: latentsData } = useStatsLatentTypesList({
    query: { enabled: stage === 3 && selectedField === "latent" },
  });
  const { data: groupsData } = useGroupsList(
    { page_size: 50, search: inputValue || undefined },
    { query: { enabled: stage === 3 && selectedField === "group" } }
  );
  const { data: rolesData } = useRolesList(
    { search: inputValue || undefined },
    { query: { enabled: stage === 3 && selectedField === "role" } }
  );
  const { data: groupTypesData } = useGroupTypesList(undefined, {
    query: { enabled: stage === 3 && selectedField === "group_type" },
  });
  // Saved queries shown in the stage-1 field picker (selecting one applies ?query=<slug>).
  const { data: queriesData } = useQueriesList(
    { page_size: 100, search: inputValue || undefined, mine: onlyMine || undefined },
    { query: { enabled: stage === 1 } }
  );

  const indexedAttrs = useMemo(
    () => (attributesData || []).filter(a => a.is_indexed && a.field_type !== "object"),
    [attributesData]
  );

  // ---- Dropdown sections (extracted hook) ----
  const { dropdownSections, rangeExample } = useDropdownSections({
    stage,
    inputValue,
    selectedField,
    selectedFieldType,
    selectedOperator,
    indexedAttrs,
    simMode,
    isRangeOp,
    isSingleNumericOp,
    facetBuckets,
    facetStats,
    catalogValues: effectiveCatalogValues,
    valueLimit,
    latentsData: latentsData as { name: string; image_count: number }[] | undefined,
    groupsData: groupsData?.results ?? [],
    rolesData: rolesData?.results ?? [],
    groupTypesData: groupTypesData?.results ?? [],
    queriesData: queriesData?.results ?? [],
    activeQuerySlug,
    currentUserEmail: user.email,
    similarityIcons: SIMILARITY_ICONS,
    hideSimilarity: isAdvancedFilter,
  });

  const flatItems = useMemo(() => dropdownSections.flatMap(s => s.items), [dropdownSections]);

  // ---- Numeric histogram (extracted hook) ----
  const { histDirty, showHistogram, histogramProps, commitHistogramRange, commitRangeFromText } = useNumericHistogram({
    selectedField,
    selectedOperator,
    isNumericField,
    isRangeOp,
    isSingleNumericOp,
    stage,
    chips,
    addChip,
    removeChip,
    resetAutocomplete,
    facetStats,
    facetHistogram,
  });

  // ---- Date range commit (creates gte + lte chip pair) ----
  const commitDateRange = useCallback(() => {
    if (!selectedField || (!dateFrom && !dateTo)) return;
    // Remove existing date chips for this field
    const toRemove = chips.filter(c => c.field === selectedField && ["gte", "lte", "gt", "lt"].includes(c.operator));
    for (const c of toRemove) removeChip(c.id);
    if (dateFrom) addChip({ field: selectedField, operator: "gte", value: dateFrom });
    if (dateTo) addChip({ field: selectedField, operator: "lte", value: dateTo });
    resetAutocomplete();
  }, [selectedField, dateFrom, dateTo, chips, addChip, removeChip, resetAutocomplete]);

  // Commit typed date range text (e.g. "2024-01-01 to 2024-06-30") — returns true if parsed
  const commitDateRangeFromText = useCallback(
    (text: string): boolean => {
      if (!selectedField) return false;
      const range = parseDateRangeInput(text);
      if (!range) return false;
      const [from, to] = range;
      const toRemove = chips.filter(c => c.field === selectedField && ["gte", "lte", "gt", "lt"].includes(c.operator));
      for (const c of toRemove) removeChip(c.id);
      addChip({ field: selectedField, operator: "gte", value: from });
      if (from !== to) addChip({ field: selectedField, operator: "lte", value: to });
      resetAutocomplete();
      return true;
    },
    [selectedField, chips, removeChip, addChip, resetAutocomplete]
  );

  const hasDateRange = isDateField && (!!dateFrom || !!dateTo);

  // ---- Combined apply for dropdown (handles histogram commit + reset) ----
  const handleDropdownApply = useCallback(() => {
    if (showHistogram) commitHistogramRange();
    else if (hasDateRange) commitDateRange();
    else resetAutocomplete();
    setIsOpen(false);
  }, [showHistogram, commitHistogramRange, hasDateRange, commitDateRange, resetAutocomplete]);

  // ---- Text query detection ----
  const looksLikeTextQuery = useCallback(
    (text: string): boolean => {
      const trimmed = text.trim();
      if (!trimmed || trimmed.length < 2) return false;
      if ((trimmed.startsWith('"') && trimmed.endsWith('"')) || (trimmed.startsWith("'") && trimmed.endsWith("'")))
        return true;
      if (trimmed.includes(" ")) {
        const lower = trimmed.toLowerCase();
        return !(
          BUILTIN_FIELDS.some(f => f.key === lower || f.label.toLowerCase() === lower) ||
          indexedAttrs.some(a => a.name.toLowerCase() === lower)
        );
      }
      const lower = trimmed.toLowerCase();
      return !(
        BUILTIN_FIELDS.some(f => f.key.toLowerCase().includes(lower) || f.label.toLowerCase().includes(lower)) ||
        indexedAttrs.some(a => a.name.toLowerCase().includes(lower))
      );
    },
    [indexedAttrs]
  );

  // ---- Default operator per field type (skip stage 2 for common cases) ----
  const DEFAULT_OPERATOR: Partial<Record<FieldType, string>> = {
    multi: "eq",
    enum: "eq",
    enum_single: "eq",
    boolean: "eq",
    string: "eq",
    numeric: "range",
    date: "gte",
  };

  // ---- Field selection (stage 1 → 2, or straight to 3 with default op) ----
  const selectField = useCallback(
    (fieldKey: string) => {
      if (isSimilarActive) setModeBrowse();
      const builtin = BUILTIN_FIELDS.find(f => f.key === fieldKey);
      let fType: FieldType;
      if (builtin) fType = builtin.fieldType;
      else if (fieldKey.startsWith("attr:")) {
        const attr = indexedAttrs.find(a => a.name === fieldKey.slice(5));
        fType = attr ? getAttrFieldType(attr) : "string";
      } else fType = "string";
      setSelectedField(fieldKey);
      setSelectedFieldType(fType);
      setInputValue("");
      setHighlightedIndex(0);

      // Auto-select default operator to skip stage 2
      const defaultOp = DEFAULT_OPERATOR[fType];
      if (defaultOp) {
        setSelectedOperator(defaultOp);
      }
    },
    [indexedAttrs, isSimilarActive, setModeBrowse]
  );

  // ---- Chip editing helpers ----
  const editChip = useCallback(
    (chip: FilterChip) => {
      if (isMultiSelectField(chip.field, selectedFieldType ?? "multi")) {
        selectField(chip.field);
        setSelectedOperator(chip.operator);
        setInputValue("");
        setIsOpen(true);
        setTimeout(() => inputRef.current?.focus(), 0);
      } else {
        removeChip(chip.id);
        selectField(chip.field);
        setSelectedOperator(chip.operator);
        setInputValue(chip.value);
        setIsOpen(true);
        setTimeout(() => {
          inputRef.current?.focus();
          inputRef.current?.select();
        }, 0);
      }
    },
    [removeChip, selectField, selectedFieldType]
  );

  const editChipGroup = useCallback(
    (field: string, operator: string) => {
      selectField(field);
      setSelectedOperator(operator);
      setInputValue("");
      setIsOpen(true);
      setTimeout(() => inputRef.current?.focus(), 0);
    },
    [selectField]
  );

  const removeChipGroup = useCallback(
    (groupChips: FilterChip[]) => {
      for (const c of groupChips) removeChip(c.id);
    },
    [removeChip]
  );

  const editNumericField = useCallback(
    (field: string) => {
      selectField(field);
      setIsOpen(true);
      setTimeout(() => inputRef.current?.focus(), 0);
    },
    [selectField]
  );

  // ---- Operator selection (stage 2 → 3) ----
  const selectOperator = useCallback(
    (opKey: string) => {
      if ((opKey === "exists" || opKey === "not_exists") && selectedField) {
        const conflicts = getNumericConflicts(chips, selectedField, opKey);
        for (const id of conflicts) removeChip(id);
        addChip({ field: selectedField, operator: opKey, value: "" });
        resetAutocomplete();
        return;
      }
      setSelectedOperator(opKey);
      setInputValue("");
      setHighlightedIndex(0);
    },
    [selectedField, chips, addChip, removeChip, resetAutocomplete]
  );

  // ---- Value commit (stage 3 → create chip) ----
  const commitValue = useCallback(
    (value: string) => {
      if (!selectedField || !selectedOperator || !value.trim()) return;
      if (selectedOperator === "range") {
        commitRangeFromText(value);
        return;
      }
      const conflicts = getNumericConflicts(chips, selectedField, selectedOperator);
      for (const id of conflicts) removeChip(id);
      addChip({ field: selectedField, operator: selectedOperator, value: value.trim() });
      if (!isMultiSelect) resetAutocomplete();
    },
    [selectedField, selectedOperator, chips, addChip, removeChip, resetAutocomplete, isMultiSelect, commitRangeFromText]
  );

  const toggleMultiValue = useCallback(
    (value: string) => {
      if (!selectedField || !selectedOperator) return;
      const existing = chips.find(
        c => c.field === selectedField && c.operator === selectedOperator && c.value === value
      );
      // Use draft operations — committed on apply/enter/esc, not on each toggle
      if (existing) removeChipDraft(existing.id);
      else addChip({ field: selectedField, operator: selectedOperator, value });
    },
    [selectedField, selectedOperator, chips, removeChipDraft, addChip]
  );

  // ---- Item selection from dropdown ----
  const handleSimFieldSelect = useCallback(
    (simKey: string) => {
      clearAllLanes();
      if (simKey === "sim:text") {
        setSimMode("text");
        setInputValue("");
        setIsOpen(false);
        setTimeout(() => inputRef.current?.focus(), 0);
      } else if (simKey === "sim:image") {
        setShowImageUpload(true);
        setIsOpen(false);
      } else if (simKey === "sim:vector") {
        setSimMode("vector");
        setInputValue("");
        setIsOpen(false);
        setTimeout(() => inputRef.current?.focus(), 0);
      }
    },
    [clearAllLanes]
  );

  const handleItemSelect = useCallback(
    (item: { key: string; disabled?: boolean }) => {
      if (item.disabled) return;
      if (item.key === SHOW_MORE_KEY) {
        // Reveal more values without committing a value or closing the dropdown.
        showMoreValues();
        return;
      }
      if (item.key.startsWith("sim:")) {
        handleSimFieldSelect(item.key);
        return;
      }
      if (item.key.startsWith("query:")) {
        // Clicking a saved query loads its stored filters into committed lanes (so the list fetches)
        // but stays collapsed: the bar shows a compact pill and the URL holds only ?query=<slug>.
        // Reset the dropdown UI but don't commitFilters() here (it would race the URL-sync effect).
        const slug = item.key.slice("query:".length);
        const saved = queriesData?.results.find(q => q.slug === slug);
        resetFilterState();
        setSimMode(null);
        setShowImageUpload(false);
        setIsOpen(false);
        if (saved) collapseToQuery(saved.slug, saved.filters as Record<string, unknown>);
        return;
      }
      if (stage === 1) selectField(item.key);
      else if (stage === 2) selectOperator(item.key);
      else if (isMultiSelect) toggleMultiValue(item.key);
      else commitValue(item.key);
    },
    [
      stage,
      selectField,
      selectOperator,
      commitValue,
      handleSimFieldSelect,
      isMultiSelect,
      toggleMultiValue,
      collapseToQuery,
      queriesData,
      resetFilterState,
      setIsOpen,
      showMoreValues,
    ]
  );

  // ---- Operator shortcut detection (stage 2) ----
  useEffect(() => {
    if (stage !== 2) return;
    const trimmed = inputValue.trim();
    if (["=", "!=", ">=", "<="].includes(trimmed)) selectOperator(OPERATOR_SHORTCUTS[trimmed]);
  }, [inputValue, stage, selectOperator]);

  // ---- Keyboard navigation ----
  const handleKeyDown = (e: React.KeyboardEvent) => {
    // Similarity mode shortcuts
    if (simMode === "text" && e.key === "Enter") {
      e.preventDefault();
      const t = inputValue.trim();
      if (t) {
        setModeSimilarText(t);
        setSimMode(null);
        setInputValue("");
      }
      return;
    }
    if (simMode === "vector" && e.key === "Enter") {
      e.preventDefault();
      const t = inputValue.trim();
      if (t) {
        setModeSimilarVector(t);
        setSimMode(null);
        setInputValue("");
      }
      return;
    }
    if (simMode && e.key === "Escape") {
      resetAutocomplete();
      return;
    }

    if (e.key === "ArrowDown") {
      e.preventDefault();
      setHighlightedIndex(i => Math.min(i + 1, flatItems.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setHighlightedIndex(i => Math.max(i - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (isDateField && stage === 3 && inputValue.trim()) {
        if (!commitDateRangeFromText(inputValue)) commitDateRange();
      } else if (isDateField && stage === 3 && !inputValue.trim() && hasDateRange) {
        commitDateRange();
      } else if (isRangeOp && stage === 3 && inputValue.trim()) {
        if (!commitRangeFromText(inputValue)) commitHistogramRange();
      } else if (showHistogram && !inputValue.trim()) {
        commitHistogramRange();
      } else if (isMultiSelect && stage === 3 && !inputValue.trim()) {
        resetAutocomplete();
      } else if (stage === 3 && inputValue.trim() && flatItems.length === 0) {
        commitValue(inputValue);
      } else if (stage === 2 && [">", "<"].includes(inputValue.trim())) {
        selectOperator(OPERATOR_SHORTCUTS[inputValue.trim()]);
      } else if (flatItems.length > 0 && highlightedIndex < flatItems.length) {
        handleItemSelect(flatItems[highlightedIndex]);
      } else if (stage === 3 && inputValue.trim()) {
        commitValue(inputValue);
      } else if (stage === 1 && inputValue.trim() && looksLikeTextQuery(inputValue)) {
        let q = inputValue.trim();
        if ((q.startsWith('"') && q.endsWith('"')) || (q.startsWith("'") && q.endsWith("'"))) q = q.slice(1, -1);
        if (q) {
          clearAllLanes();
          setModeSimilarText(q);
          setInputValue("");
        }
      }
    } else if (e.key === "Escape") {
      if (showHistogram) commitHistogramRange();
      else if (isMultiSelect && stage === 3) resetAutocomplete();
      else if (selectedOperator) {
        setSelectedOperator(null);
        setInputValue("");
        setHighlightedIndex(0);
      } else if (selectedField) resetAutocomplete();
      else {
        setIsOpen(false);
        inputRef.current?.blur();
      }
    } else if (e.key === "Tab" && isOpen) {
      if (showHistogram) {
        e.preventDefault();
        commitHistogramRange();
      } else if (flatItems.length > 0 && highlightedIndex < flatItems.length) {
        e.preventDefault();
        handleItemSelect(flatItems[highlightedIndex]);
      }
    } else if (e.key === "Backspace" && inputValue === "") {
      if (isMultiSelect && stage === 3) resetAutocomplete();
      else if (showHistogram) resetAutocomplete();
      else if (selectedOperator) {
        setSelectedOperator(null);
        setHighlightedIndex(0);
      } else if (selectedField) resetAutocomplete();
      else if (isSimilarActive) setModeBrowse();
      else if (chips.length > 0) removeChip(chips[chips.length - 1].id);
    }
  };

  // ---- Input change ----
  const handleInputChange = (e: React.ChangeEvent<HTMLInputElement>) => {
    const val = e.target.value;
    setInputValue(val);
    setHighlightedIndex(0);
    if (simMode) return;
    setIsOpen(true);

    if (stage === 1) {
      const colonIndex = val.indexOf(":");
      if (colonIndex > 0) {
        const fieldPart = val.substring(0, colonIndex).toLowerCase();
        const valuePart = val.substring(colonIndex + 1);
        const matchedBuiltin = BUILTIN_FIELDS.find(f => f.key === fieldPart || f.label.toLowerCase() === fieldPart);
        const matchedAttr = !matchedBuiltin ? indexedAttrs.find(a => a.name.toLowerCase() === fieldPart) : null;
        if (matchedBuiltin || matchedAttr) {
          const fieldKey = matchedBuiltin ? matchedBuiltin.key : `attr:${matchedAttr!.name}`;
          selectField(fieldKey);
          setSelectedOperator("eq");
          setInputValue(valuePart);
          return;
        }
      }
    }
  };

  // ---- Click outside ----
  // Uses data-filter-container attribute so both the main bar and the dialog
  // can contain filter elements without interfering with each other.
  useEffect(() => {
    const handleClickOutside = (e: MouseEvent) => {
      if (!(e.target instanceof Node)) return;
      const target = e.target as HTMLElement;
      if (target.closest?.("[data-filter-container]")) return;
      if (showHistogram && histDirty && selectedField) commitHistogramRange();
      else {
        setIsOpen(false);
        if (!simMode) resetAutocomplete();
      }
    };
    document.addEventListener("mousedown", handleClickOutside);
    return () => document.removeEventListener("mousedown", handleClickOutside);
  }, [resetAutocomplete, simMode, showHistogram, histDirty, selectedField, commitHistogramRange]);

  // ---- Effects ----
  useEffect(() => {
    setHighlightedIndex(0);
  }, [flatItems.length]);
  useEffect(() => {
    if (!dropdownRef.current) return;
    dropdownRef.current.querySelector(`[data-index="${highlightedIndex}"]`)?.scrollIntoView({ block: "nearest" });
  }, [highlightedIndex]);

  // ---- Similarity display ----
  const simLabel = isSimilarActive
    ? similarText
      ? "Text"
      : similarFile
        ? "Image"
        : similarVector
          ? "Vector"
          : "Similar"
    : null;
  const simValue = isSimilarActive
    ? similarText || (similarFile ? "Uploaded file" : similarVector ? "Embedding" : similarImage ? similarImage.id : "")
    : "";

  // ---- Change operator (set a new one, or clear to go back to stage 2) ----
  const changeOperator = useCallback(
    (op?: string) => {
      // exists / not_exists create a chip immediately (no value needed)
      if ((op === "exists" || op === "not_exists") && selectedField) {
        const conflicts = getNumericConflicts(chips, selectedField, op);
        for (const id of conflicts) removeChip(id);
        addChip({ field: selectedField, operator: op, value: "" });
        resetAutocomplete();
        return;
      }
      setSelectedOperator(op ?? null);
      setInputValue("");
      setDateFrom("");
      setDateTo("");
      setHighlightedIndex(0);
      setIsOpen(true);
    },
    [selectedField, chips, addChip, removeChip, resetAutocomplete]
  );

  // ---- Placeholder ----
  const placeholder = simMode
    ? simMode === "text"
      ? "Describe the image and press Enter..."
      : "Paste embedding vector and press Enter..."
    : stage === 3
      ? isDateField
        ? "Type range, e.g. 2024-01-01 to 2024-12-31"
        : isRangeOp
          ? `Type range (e.g. ${rangeExample || "500-1000"}) or use slider...`
          : showHistogram
            ? "Type a value or use slider..."
            : isMultiSelect
              ? "Search values... (Enter/Esc to close)"
              : "Enter value..."
      : stage === 2
        ? "Select operator (type =, >, <, !=, ...)"
        : chips.length > 0 || isSimilarActive
          ? "Add filter..."
          : "Filter or search images...";

  return {
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
    setDateRange: useCallback((from: string, to: string) => {
      setDateFrom(from);
      setDateTo(to);
    }, []),
    commitDateRange,
    hasDateRange,
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
    clearChips,
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
  };
}
