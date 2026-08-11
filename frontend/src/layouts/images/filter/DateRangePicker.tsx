import React, { useCallback, useMemo, useState } from "react";
import { twMerge } from "tailwind-merge";
import { ChevronLeftIcon, ChevronRightIcon } from "@heroicons/react/20/solid";

interface DateRangePickerProps {
  /** Start date in YYYY-MM-DD format */
  startDate: string;
  /** End date in YYYY-MM-DD format */
  endDate: string;
  /** Called when the range changes */
  onChange: (start: string, end: string) => void;
  /** Compact mode for sidebar (smaller cells) */
  compact?: boolean;
}

const DAYS = ["Mo", "Tu", "We", "Th", "Fr", "Sa", "Su"];
const MONTHS = [
  "January",
  "February",
  "March",
  "April",
  "May",
  "June",
  "July",
  "August",
  "September",
  "October",
  "November",
  "December",
];

function toDateStr(d: Date): string {
  const y = d.getFullYear();
  const m = String(d.getMonth() + 1).padStart(2, "0");
  const day = String(d.getDate()).padStart(2, "0");
  return `${y}-${m}-${day}`;
}

function parseDate(s: string): Date | null {
  if (!s) return null;
  const d = new Date(s + "T00:00:00");
  return isNaN(d.getTime()) ? null : d;
}

function getMonthDays(year: number, month: number): { date: Date; isCurrentMonth: boolean }[] {
  const firstDay = new Date(year, month, 1);
  const lastDay = new Date(year, month + 1, 0);

  // Monday = 0, Sunday = 6
  let startDow = firstDay.getDay() - 1;
  if (startDow < 0) startDow = 6;

  const days: { date: Date; isCurrentMonth: boolean }[] = [];

  // Fill leading days from previous month
  for (let i = startDow - 1; i >= 0; i--) {
    const d = new Date(year, month, -i);
    days.push({ date: d, isCurrentMonth: false });
  }

  // Current month days
  for (let i = 1; i <= lastDay.getDate(); i++) {
    days.push({ date: new Date(year, month, i), isCurrentMonth: true });
  }

  // Fill trailing days to complete last week
  while (days.length % 7 !== 0) {
    const d = new Date(year, month + 1, days.length - startDow - lastDay.getDate() + 1);
    days.push({ date: d, isCurrentMonth: false });
  }

  return days;
}

export const DateRangePicker: React.FC<DateRangePickerProps> = ({ startDate, endDate, onChange, compact = false }) => {
  const today = useMemo(() => new Date(), []);
  const [viewYear, setViewYear] = useState(() => {
    const d = parseDate(endDate) || parseDate(startDate) || today;
    return d.getFullYear();
  });
  const [viewMonth, setViewMonth] = useState(() => {
    const d = parseDate(endDate) || parseDate(startDate) || today;
    return d.getMonth();
  });

  // Track which part of the range is being selected: "start" or "end"
  const [selecting, setSelecting] = useState<"start" | "end">("start");
  // Hover date for preview
  const [hoverDate, setHoverDate] = useState<string | null>(null);

  const days = useMemo(() => getMonthDays(viewYear, viewMonth), [viewYear, viewMonth]);

  const prevMonth = useCallback(() => {
    setViewMonth(m => {
      if (m === 0) {
        setViewYear(y => y - 1);
        return 11;
      }
      return m - 1;
    });
  }, []);

  const nextMonth = useCallback(() => {
    setViewMonth(m => {
      if (m === 11) {
        setViewYear(y => y + 1);
        return 0;
      }
      return m + 1;
    });
  }, []);

  const handleDayClick = useCallback(
    (dateStr: string) => {
      if (selecting === "start") {
        // If clicked date is after current end, reset end
        if (endDate && dateStr > endDate) {
          onChange(dateStr, "");
        } else {
          onChange(dateStr, endDate);
        }
        setSelecting("end");
      } else {
        // Selecting end
        if (startDate && dateStr < startDate) {
          // Clicked before start — treat as new start
          onChange(dateStr, "");
          setSelecting("end");
        } else {
          onChange(startDate, dateStr);
          setSelecting("start");
        }
      }
    },
    [selecting, startDate, endDate, onChange]
  );

  const todayStr = toDateStr(today);
  const cellSize = compact ? "size-6" : "size-7";
  const fontSize = compact ? "text-[10px]" : "text-xs";

  return (
    <div className="select-none">
      {/* Month navigation */}
      <div className="flex items-center justify-between px-1 mb-1">
        <button
          type="button"
          onClick={prevMonth}
          className="p-0.5 rounded hover:bg-black/5 dark:hover:bg-white/5 cursor-pointer"
        >
          <ChevronLeftIcon className="size-4 opacity-60" />
        </button>
        <span className={twMerge("font-medium", fontSize)}>
          {MONTHS[viewMonth]} {viewYear}
        </span>
        <button
          type="button"
          onClick={nextMonth}
          className="p-0.5 rounded hover:bg-black/5 dark:hover:bg-white/5 cursor-pointer"
        >
          <ChevronRightIcon className="size-4 opacity-60" />
        </button>
      </div>

      {/* Day-of-week headers */}
      <div className="grid grid-cols-7 text-center">
        {DAYS.map(d => (
          <div key={d} className={twMerge(cellSize, "flex items-center justify-center", fontSize, "opacity-40")}>
            {d}
          </div>
        ))}
      </div>

      {/* Calendar grid */}
      <div className="grid grid-cols-7">
        {days.map(({ date, isCurrentMonth }, i) => {
          const dateStr = toDateStr(date);
          const isStart = dateStr === startDate;
          const isEnd = dateStr === endDate;
          const isToday = dateStr === todayStr;

          // Determine if in range (including hover preview)
          let inRange = false;
          const effectiveEnd = selecting === "end" && hoverDate ? hoverDate : endDate;
          if (startDate && effectiveEnd && dateStr >= startDate && dateStr <= effectiveEnd) {
            inRange = true;
          }
          // Preview when selecting start
          if (
            selecting === "start" &&
            hoverDate &&
            endDate &&
            hoverDate <= endDate &&
            dateStr >= hoverDate &&
            dateStr <= endDate
          ) {
            inRange = true;
          }

          const isEndpoint = isStart || isEnd;

          return (
            <button
              key={i}
              type="button"
              onClick={() => handleDayClick(dateStr)}
              onMouseEnter={() => setHoverDate(dateStr)}
              onMouseLeave={() => setHoverDate(null)}
              className={twMerge(
                cellSize,
                "flex items-center justify-center cursor-pointer transition-colors",
                fontSize,
                !isCurrentMonth && "opacity-25",
                isCurrentMonth && !inRange && !isEndpoint && "hover:bg-black/5 dark:hover:bg-white/5",
                inRange && !isEndpoint && "bg-brand-100 dark:bg-brand-900/40",
                isEndpoint && "bg-brand-500 text-white rounded-md font-bold",
                isToday && !isEndpoint && "font-bold underline"
              )}
            >
              {date.getDate()}
            </button>
          );
        })}
      </div>

      {/* Range summary */}
      <div className={twMerge("flex items-center justify-between mt-1.5 px-1 tabular-nums", fontSize, "opacity-50")}>
        <span>{startDate || "Start"}</span>
        <span>→</span>
        <span>{endDate || "End"}</span>
      </div>
    </div>
  );
};
