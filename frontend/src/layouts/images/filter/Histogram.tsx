import React, { useCallback, useMemo } from "react";
import { twMerge } from "tailwind-merge";

interface HistogramProps {
  bins: { key: number; doc_count: number }[];
  min: number;
  max: number;
  mode: "range" | "single";
  /** For range mode: start of selected range. For single mode: unused. */
  rangeStart: number | null;
  /** For range mode: end of selected range. For single mode: the selected value. */
  rangeEnd: number | null;
  onRangeChange: (start: number | null, end: number | null) => void;
  onApply?: () => void;
}

export const Histogram: React.FC<HistogramProps> = ({
  bins,
  min,
  max,
  mode,
  rangeStart,
  rangeEnd,
  onRangeChange,
  onApply,
}) => {
  const maxCount = useMemo(() => Math.max(...bins.map(b => b.doc_count), 1), [bins]);

  const step = useMemo(() => {
    if (bins.length < 2) return 1;
    return bins[1].key - bins[0].key;
  }, [bins]);

  // Slider range covers the full extent of histogram bins
  const sliderMin = bins.length > 0 ? bins[0].key : min;
  const sliderMax = bins.length > 0 ? bins[bins.length - 1].key + step : max;

  // --- Range mode handlers ---
  const handleMinChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const val = Number(e.target.value);
      const clamped = rangeEnd !== null ? Math.min(val, rangeEnd) : val;
      onRangeChange(clamped <= sliderMin ? null : clamped, rangeEnd);
    },
    [sliderMin, rangeEnd, onRangeChange]
  );

  const handleMaxChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const val = Number(e.target.value);
      const clamped = rangeStart !== null ? Math.max(val, rangeStart) : val;
      onRangeChange(rangeStart, clamped >= sliderMax ? null : clamped);
    },
    [sliderMax, rangeStart, onRangeChange]
  );

  // --- Single mode handler ---
  const handleSingleChange = useCallback(
    (e: React.ChangeEvent<HTMLInputElement>) => {
      const val = Number(e.target.value);
      onRangeChange(null, val);
    },
    [onRangeChange]
  );

  const effectiveStart = rangeStart ?? sliderMin;
  const effectiveEnd = rangeEnd ?? sliderMax;
  const singleValue = rangeEnd ?? sliderMin;

  // Key handler on the histogram container so Enter/Tab apply without input focus
  const handleKeyDown = useCallback(
    (e: React.KeyboardEvent) => {
      if (e.key === "Enter" || e.key === "Tab") {
        e.preventDefault();
        e.stopPropagation();
        onApply?.();
      }
    },
    [onApply]
  );

  return (
    <div className="px-3 py-2 space-y-2" onKeyDown={handleKeyDown}>
      {/* Histogram bars */}
      <div className="flex items-end gap-px h-20">
        {bins.map(bin => {
          const pct = (bin.doc_count / maxCount) * 100;
          const binEnd = bin.key + step;
          const inRange =
            mode === "range" ? bin.key >= effectiveStart && binEnd <= effectiveEnd : bin.key <= singleValue;
          return (
            <div
              key={bin.key}
              className={twMerge(
                "flex-1 rounded-t-sm transition-opacity min-w-[2px]",
                inRange ? "bg-brand-400 dark:bg-brand-500" : "bg-black/10 dark:bg-white/10"
              )}
              style={{ height: `${Math.max(pct, 2)}%` }}
              title={`${bin.key}: ${bin.doc_count.toLocaleString()}`}
            />
          );
        })}
      </div>

      {/* Sliders */}
      <div className="relative h-5">
        {mode === "range" ? (
          <>
            <input
              type="range"
              min={sliderMin}
              max={sliderMax}
              step={step}
              value={effectiveStart}
              onChange={handleMinChange}
              className="absolute w-full h-1 appearance-none bg-transparent pointer-events-none [&::-webkit-slider-thumb]:pointer-events-auto [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:h-3.5 [&::-webkit-slider-thumb]:w-3.5 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-brand-500 [&::-webkit-slider-thumb]:cursor-pointer [&::-webkit-slider-thumb]:relative [&::-webkit-slider-thumb]:z-10"
            />
            <input
              type="range"
              min={sliderMin}
              max={sliderMax}
              step={step}
              value={effectiveEnd}
              onChange={handleMaxChange}
              className="absolute w-full h-1 appearance-none bg-transparent pointer-events-none [&::-webkit-slider-thumb]:pointer-events-auto [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:h-3.5 [&::-webkit-slider-thumb]:w-3.5 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-brand-500 [&::-webkit-slider-thumb]:cursor-pointer"
            />
          </>
        ) : (
          <input
            type="range"
            min={sliderMin}
            max={sliderMax}
            step={step}
            value={singleValue}
            onChange={handleSingleChange}
            className="absolute w-full h-1 appearance-none bg-transparent pointer-events-none [&::-webkit-slider-thumb]:pointer-events-auto [&::-webkit-slider-thumb]:appearance-none [&::-webkit-slider-thumb]:h-3.5 [&::-webkit-slider-thumb]:w-3.5 [&::-webkit-slider-thumb]:rounded-full [&::-webkit-slider-thumb]:bg-brand-500 [&::-webkit-slider-thumb]:cursor-pointer"
          />
        )}
      </div>

      {/* Labels */}
      <div className="flex justify-between text-[10px] text-black/40 dark:text-white/40 tabular-nums">
        {mode === "range" ? (
          <>
            <span>{effectiveStart.toLocaleString()}</span>
            <span>{effectiveEnd.toLocaleString()}</span>
          </>
        ) : (
          <span className="w-full text-center">{singleValue.toLocaleString()}</span>
        )}
      </div>
    </div>
  );
};
