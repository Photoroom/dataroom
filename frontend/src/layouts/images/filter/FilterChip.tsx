import React from "react";
import { twMerge } from "tailwind-merge";
import { XMarkIcon } from "@heroicons/react/20/solid";
import { FilterChip } from "../../../context/ImageListDataContext";
import { getFieldLabel, getOperatorSymbol, getChipDisplayValue, TYPE_BADGE_CLASSES } from "./constants";

// -------------------- Chip display --------------------

export const ChipDisplay: React.FC<{ chip: FilterChip; onRemove: () => void; onEdit: () => void }> = ({
  chip,
  onRemove,
  onEdit,
}) => (
  <span
    className={twMerge(
      "inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs",
      "bg-brand-100 text-brand-800 dark:bg-brand-900 dark:text-brand-200",
      "whitespace-nowrap shrink-0 cursor-pointer hover:bg-brand-200 dark:hover:bg-brand-800 transition-colors"
    )}
    onClick={e => {
      e.stopPropagation();
      onEdit();
    }}
  >
    <span className="opacity-60">{getFieldLabel(chip.field)}</span>
    {chip.operator === "exists" ? (
      <span className="font-medium">exists</span>
    ) : chip.operator === "not_exists" ? (
      <span className="font-medium">not exists</span>
    ) : (
      <>
        <span className="opacity-40">{getOperatorSymbol(chip.operator, chip.field)}</span>
        <span className="font-medium">{getChipDisplayValue(chip)}</span>
      </>
    )}
    <button
      type="button"
      onClick={e => {
        e.stopPropagation();
        onRemove();
      }}
      className="ml-0.5 hover:opacity-100 opacity-60 cursor-pointer"
    >
      <XMarkIcon className="size-3.5" />
    </button>
  </span>
);

// -------------------- Grouped chip display --------------------

const MAX_VISIBLE_VALUES = 2;

export const GroupedChipDisplay: React.FC<{
  chips: FilterChip[];
  onRemoveAll: () => void;
  onEdit: () => void;
}> = ({ chips, onRemoveAll, onEdit }) => {
  const field = chips[0].field;
  const operator = chips[0].operator;
  const values = chips.map(c => getChipDisplayValue(c));
  const visible = values.slice(0, MAX_VISIBLE_VALUES);
  const remaining = values.length - visible.length;

  return (
    <span
      className={twMerge(
        "inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs",
        "bg-brand-100 text-brand-800 dark:bg-brand-900 dark:text-brand-200",
        "whitespace-nowrap shrink-0 cursor-pointer hover:bg-brand-200 dark:hover:bg-brand-800 transition-colors"
      )}
      onClick={e => {
        e.stopPropagation();
        onEdit();
      }}
    >
      <span className="opacity-60">{getFieldLabel(field)}</span>
      <span className="opacity-40">{getOperatorSymbol(operator, field)}</span>
      <span className="font-medium">
        {visible.join(", ")}
        {remaining > 0 && <span className="opacity-60"> +{remaining} more</span>}
      </span>
      <button
        type="button"
        onClick={e => {
          e.stopPropagation();
          onRemoveAll();
        }}
        className="ml-0.5 hover:opacity-100 opacity-60 cursor-pointer"
      >
        <XMarkIcon className="size-3.5" />
      </button>
    </span>
  );
};

// -------------------- Combined numeric chip display --------------------

export const CombinedNumericChipDisplay: React.FC<{
  chips: FilterChip[];
  onRemoveAll: () => void;
  onEdit: () => void;
}> = ({ chips, onRemoveAll, onEdit }) => {
  const field = chips[0].field;

  return (
    <span
      className={twMerge(
        "inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs",
        "bg-brand-100 text-brand-800 dark:bg-brand-900 dark:text-brand-200",
        "whitespace-nowrap shrink-0 cursor-pointer hover:bg-brand-200 dark:hover:bg-brand-800 transition-colors"
      )}
      onClick={e => {
        e.stopPropagation();
        onEdit();
      }}
    >
      <span className="opacity-60">{getFieldLabel(field)}</span>
      <span className="font-medium">
        {chips.map((c, i) => (
          <span key={c.id}>
            {i > 0 && <span className="opacity-40">, </span>}
            {c.operator === "exists" ? (
              "exists"
            ) : c.operator === "not_exists" ? (
              "not exists"
            ) : (
              <>
                <span className="opacity-40">{getOperatorSymbol(c.operator)}</span>
                {getChipDisplayValue(c)}
              </>
            )}
          </span>
        ))}
      </span>
      <button
        type="button"
        onClick={e => {
          e.stopPropagation();
          onRemoveAll();
        }}
        className="ml-0.5 hover:opacity-100 opacity-60 cursor-pointer"
      >
        <XMarkIcon className="size-3.5" />
      </button>
    </span>
  );
};

// -------------------- Similarity chip --------------------

export const SimilarityChip: React.FC<{ label: string; value: string; onRemove: () => void }> = ({
  label,
  value,
  onRemove,
}) => (
  <span
    className={twMerge(
      "inline-flex items-center gap-1 px-2 py-0.5 rounded-md text-xs",
      "bg-amber-100 text-amber-800 dark:bg-amber-900 dark:text-amber-200",
      "whitespace-nowrap shrink-0"
    )}
  >
    <span className="opacity-60">{label}</span>
    <span className="font-medium truncate max-w-[12rem]">{value}</span>
    <button
      type="button"
      onClick={e => {
        e.stopPropagation();
        onRemove();
      }}
      className="ml-0.5 hover:opacity-100 opacity-60 cursor-pointer"
    >
      <XMarkIcon className="size-3.5" />
    </button>
  </span>
);

// -------------------- Type badge --------------------

export const TypeBadge: React.FC<{ type: string }> = ({ type }) => (
  <span
    className={twMerge(
      "px-1.5 py-0.5 rounded text-[10px] font-medium leading-none",
      TYPE_BADGE_CLASSES[type] || "bg-gray-100 text-gray-600 dark:bg-gray-800 dark:text-gray-400"
    )}
  >
    {type}
  </span>
);
