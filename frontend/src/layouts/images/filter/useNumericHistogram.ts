import { useCallback, useEffect, useRef, useState } from "react";
import { FilterChip } from "../../../context/ImageListDataContext";
import { getNumericConflicts, RANGE_REPLACES, parseRangeInput } from "./numericConflicts";
export interface HistogramBin {
  key: number;
  doc_count: number;
}

interface UseNumericHistogramArgs {
  selectedField: string | null;
  selectedOperator: string | null;
  isNumericField: boolean;
  isRangeOp: boolean;
  isSingleNumericOp: boolean;
  stage: 1 | 2 | 3;
  chips: FilterChip[];
  addChip: (chip: Omit<FilterChip, "id">) => void;
  removeChip: (id: string) => void;
  resetAutocomplete: () => void;
  facetStats: { min: number; max: number; count: number; avg: number; sum: number } | null;
  facetHistogram: HistogramBin[];
}

export function useNumericHistogram({
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
}: UseNumericHistogramArgs) {
  const [histRangeStart, setHistRangeStart] = useState<number | null>(null);
  const [histRangeEnd, setHistRangeEnd] = useState<number | null>(null);
  const [histDirty, setHistDirty] = useState(false);

  // Reset when field changes
  useEffect(() => {
    setHistRangeStart(null);
    setHistRangeEnd(null);
    setHistDirty(false);
  }, [selectedField]);

  // Initialize from existing chips (once per field+operator)
  const histInitRef = useRef<string | null>(null);
  useEffect(() => {
    if (!selectedField || !isNumericField || stage !== 3) return;
    const initKey = `${selectedField}:${selectedOperator}`;
    if (histInitRef.current === initKey) return;
    histInitRef.current = initKey;

    if (isRangeOp) {
      const gteChip = chips.find(c => c.field === selectedField && c.operator === "gte");
      const lteChip = chips.find(c => c.field === selectedField && c.operator === "lte");
      setHistRangeStart(gteChip ? Number(gteChip.value) : null);
      setHistRangeEnd(lteChip ? Number(lteChip.value) : null);
    } else if (selectedOperator && selectedOperator !== "ne") {
      const existing = chips.find(c => c.field === selectedField && c.operator === selectedOperator);
      setHistRangeStart(null);
      setHistRangeEnd(existing ? Number(existing.value) : null);
    }
    setHistDirty(false);
  }, [selectedField, isNumericField, stage, selectedOperator, isRangeOp, chips]);

  const handleRangeChange = useCallback((start: number | null, end: number | null) => {
    setHistRangeStart(start);
    setHistRangeEnd(end);
    setHistDirty(true);
  }, []);

  // Commit the current histogram selection as chips
  const commitHistogramRange = useCallback(() => {
    if (!selectedField || !histDirty) {
      resetAutocomplete();
      return;
    }

    if (isRangeOp) {
      const toRemove = chips.filter(c => c.field === selectedField && RANGE_REPLACES.has(c.operator));
      for (const c of toRemove) removeChip(c.id);
      if (histRangeStart !== null) addChip({ field: selectedField, operator: "gte", value: String(histRangeStart) });
      if (histRangeEnd !== null) addChip({ field: selectedField, operator: "lte", value: String(histRangeEnd) });
    } else if (selectedOperator && histRangeEnd !== null) {
      const conflicts = getNumericConflicts(chips, selectedField, selectedOperator);
      for (const id of conflicts) removeChip(id);
      addChip({ field: selectedField, operator: selectedOperator, value: String(histRangeEnd) });
    }

    resetAutocomplete();
  }, [
    selectedField,
    selectedOperator,
    histDirty,
    isRangeOp,
    histRangeStart,
    histRangeEnd,
    chips,
    removeChip,
    addChip,
    resetAutocomplete,
  ]);

  // Commit a typed range string (e.g. "500-600") — returns true if parsed successfully
  const commitRangeFromText = useCallback(
    (text: string): boolean => {
      if (!selectedField) return false;
      const range = parseRangeInput(text);
      if (!range) return false;
      const [lo, hi] = range;
      const toRemove = chips.filter(c => c.field === selectedField && RANGE_REPLACES.has(c.operator));
      for (const c of toRemove) removeChip(c.id);
      addChip({ field: selectedField, operator: "gte", value: String(lo) });
      addChip({ field: selectedField, operator: "lte", value: String(hi) });
      resetAutocomplete();
      return true;
    },
    [selectedField, chips, removeChip, addChip, resetAutocomplete]
  );

  // Whether the histogram should be visible
  const showHistogram =
    isNumericField &&
    stage === 3 &&
    (isRangeOp || isSingleNumericOp) &&
    facetHistogram.length > 0 &&
    facetStats !== null;

  const histogramMode: "range" | "single" = isRangeOp ? "range" : "single";

  const histogramProps =
    showHistogram && facetStats
      ? {
          bins: facetHistogram,
          min: facetStats.min,
          max: facetStats.max,
          mode: histogramMode,
          rangeStart: histRangeStart,
          rangeEnd: histRangeEnd,
          onRangeChange: handleRangeChange,
          onApply: commitHistogramRange,
        }
      : undefined;

  return {
    histDirty,
    showHistogram,
    histogramProps,
    commitHistogramRange,
    commitRangeFromText,
  };
}
