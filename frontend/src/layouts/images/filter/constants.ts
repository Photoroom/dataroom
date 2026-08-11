import type React from "react";
import { FilterChip } from "../../../context/ImageListDataContext";
import { AttributeField } from "../../../api/client.schemas";

// -------------------- Field & Operator types --------------------

export type FieldType = "numeric" | "string" | "multi" | "enum" | "enum_single" | "boolean" | "date";

export interface BuiltinField {
  key: string;
  label: string;
  category: string;
  fieldType: FieldType;
  typeBadge?: string;
}

export interface OperatorDef {
  key: string;
  symbol: string;
  label: string;
}

export interface DropdownSection {
  header: string;
  items: DropdownItem[];
}

export interface DropdownItem {
  key: string;
  label: string;
  description?: string;
  typeBadge?: string;
  count?: number;
  rightLabel?: string;
  disabled?: boolean;
  icon?: React.ComponentType<{ className?: string }>;
  /** Render the label with emphasis (e.g. saved queries the current user owns). */
  emphasized?: boolean;
  /** Synthetic "Show more" row — reveals the next page of values instead of committing a value. */
  isShowMore?: boolean;
}

// Special item key for the "Show more" row appended to a paginated value list.
export const SHOW_MORE_KEY = "__show_more__";

// -------------------- Constants --------------------

export const OPERATORS_BY_TYPE: Record<FieldType, OperatorDef[]> = {
  numeric: [
    { key: "range", symbol: "~", label: "in range" },
    { key: "eq", symbol: "=", label: "equals" },
    { key: "ne", symbol: "!=", label: "not equals" },
    { key: "gt", symbol: ">", label: "greater than" },
    { key: "gte", symbol: ">=", label: "greater or equal" },
    { key: "lt", symbol: "<", label: "less than" },
    { key: "lte", symbol: "<=", label: "less or equal" },
    { key: "exists", symbol: "?", label: "exists" },
    { key: "not_exists", symbol: "!?", label: "not exists" },
  ],
  string: [
    { key: "eq", symbol: "=", label: "equals" },
    { key: "ne", symbol: "!=", label: "not equals" },
    { key: "match_phrase", symbol: "~", label: "contains phrase" },
    { key: "not_match_phrase", symbol: "!~", label: "not contains phrase" },
    { key: "match", symbol: "~*", label: "contains any word" },
    { key: "not_match", symbol: "!~*", label: "not contains any word" },
    { key: "prefix", symbol: "^", label: "starts with" },
    { key: "not_prefix", symbol: "!^", label: "not starts with" },
    { key: "exists", symbol: "?", label: "exists" },
    { key: "not_exists", symbol: "!?", label: "not exists" },
  ],
  multi: [
    { key: "eq", symbol: "=", label: "is" },
    { key: "ne", symbol: "!=", label: "is not" },
  ],
  enum: [
    { key: "eq", symbol: "=", label: "is" },
    { key: "ne", symbol: "!=", label: "is not" },
  ],
  enum_single: [
    { key: "eq", symbol: "=", label: "is" },
    { key: "ne", symbol: "!=", label: "is not" },
  ],
  boolean: [
    { key: "eq", symbol: "=", label: "is" },
    { key: "ne", symbol: "!=", label: "is not" },
    { key: "exists", symbol: "?", label: "exists" },
    { key: "not_exists", symbol: "!?", label: "not exists" },
  ],
  date: [
    { key: "gt", symbol: ">", label: "after" },
    { key: "gte", symbol: ">=", label: "on or after" },
    { key: "lt", symbol: "<", label: "before" },
    { key: "lte", symbol: "<=", label: "on or before" },
  ],
};

export const BUILTIN_FIELDS: BuiltinField[] = [
  // Organization first (most commonly used)
  { key: "source", label: "Source", category: "Organization", fieldType: "multi" },
  { key: "tag", label: "Tag", category: "Organization", fieldType: "multi" },
  { key: "dataset", label: "Dataset", category: "Organization", fieldType: "multi" },
  { key: "duplicate_state", label: "Duplicate State", category: "Organization", fieldType: "enum" },
  { key: "latent", label: "Latent", category: "Organization", fieldType: "multi" },
  { key: "group", label: "Group", category: "Organization", fieldType: "multi" },
  { key: "group_type", label: "Group Type", category: "Organization", fieldType: "enum_single" },
  { key: "role", label: "Role", category: "Organization", fieldType: "multi" },
  // Image Properties
  { key: "width", label: "Width", category: "Image Properties", fieldType: "numeric", typeBadge: "number" },
  { key: "height", label: "Height", category: "Image Properties", fieldType: "numeric", typeBadge: "number" },
  { key: "short_edge", label: "Short Edge", category: "Image Properties", fieldType: "numeric", typeBadge: "number" },
  {
    key: "pixel_count",
    label: "Pixel Count",
    category: "Image Properties",
    fieldType: "numeric",
    typeBadge: "number",
  },
  {
    key: "aspect_ratio",
    label: "Aspect Ratio",
    category: "Image Properties",
    fieldType: "numeric",
    typeBadge: "number",
  },
  {
    key: "aspect_ratio_fraction",
    label: "Aspect Ratio Fraction",
    category: "Image Properties",
    fieldType: "string",
    typeBadge: "string",
  },
  // Dates
  { key: "date_created", label: "Date Created", category: "Dates", fieldType: "date", typeBadge: "date" },
  { key: "date_updated", label: "Date Updated", category: "Dates", fieldType: "date", typeBadge: "date" },
];

export const SIMILARITY_FIELDS = [
  {
    key: "sim:text",
    label: "Text Search",
    iconName: "DocumentTextIcon" as const,
    description: "Search by text description",
  },
  {
    key: "sim:image",
    label: "Image Search",
    iconName: "PhotoIcon" as const,
    description: "Upload an image to find similar",
  },
  {
    key: "sim:vector",
    label: "Vector Search",
    iconName: "ArrowsRightLeftIcon" as const,
    description: "Paste an embedding vector",
  },
];

export const OPERATOR_SHORTCUTS: Record<string, string> = {
  "=": "eq",
  "!=": "ne",
  ">": "gt",
  ">=": "gte",
  "<": "lt",
  "<=": "lte",
};

export const TYPE_BADGE_CLASSES: Record<string, string> = {
  string: "bg-blue-100 text-blue-700 dark:bg-blue-900/50 dark:text-blue-300",
  number: "bg-green-100 text-green-700 dark:bg-green-900/50 dark:text-green-300",
  integer: "bg-green-100 text-green-700 dark:bg-green-900/50 dark:text-green-300",
  boolean: "bg-purple-100 text-purple-700 dark:bg-purple-900/50 dark:text-purple-300",
  date: "bg-orange-100 text-orange-700 dark:bg-orange-900/50 dark:text-orange-300",
};

export const DUPLICATE_STATE_LABELS: Record<string, string> = {
  None: "Unprocessed",
  "1": "Original",
  "2": "Duplicate",
};

// -------------------- Multi-select --------------------

export const MULTI_SELECT_FIELDS = new Set([
  "source",
  "tag",
  "dataset",
  "latent",
  "group",
  "role",
  "aspect_ratio_fraction",
  "duplicate_state",
]);

export function isMultiSelectField(field: string, fieldType: FieldType): boolean {
  if (MULTI_SELECT_FIELDS.has(field)) return true;
  // Enum attributes are also multi-select
  if (field.startsWith("attr:") && fieldType === "enum") return true;
  return false;
}

// -------------------- Value catalog --------------------

// Discrete fields whose distinct-value set can grow unbounded. Their full value list is
// loaded once from /api/images/field_catalog/, cached client-side, and filtered locally —
// instead of only ever showing the top-N most frequent values (as the facets endpoint does).
export const CATALOG_FIELDS = new Set(["source", "tag", "dataset"]);

export function isCatalogField(field: string, fieldType?: FieldType): boolean {
  if (CATALOG_FIELDS.has(field)) return true;
  // Free-text (keyword) attributes are unbounded too. Enum attributes use their static
  // choice list; numeric/boolean/date attributes aren't term lists, so neither needs a catalog.
  if (field.startsWith("attr:") && fieldType === "string") return true;
  return false;
}

// -------------------- Helpers --------------------

export function getOperatorSymbol(op: string, field?: string): string {
  // A dataset "prefix" chip matches every version of a slug — render it clearly.
  if (field === "dataset" && op === "prefix") return "any version of";
  for (const ops of Object.values(OPERATORS_BY_TYPE)) {
    const found = ops.find(o => o.key === op);
    if (found) return found.symbol;
  }
  return op;
}

export function getFieldLabel(fieldKey: string): string {
  const builtin = BUILTIN_FIELDS.find(f => f.key === fieldKey);
  if (builtin) return builtin.label;
  if (fieldKey.startsWith("attr:")) return fieldKey.slice(5);
  if (fieldKey === "has_attributes") return "Has Attr";
  if (fieldKey === "lacks_attributes") return "Lacks Attr";
  return fieldKey;
}

export function getChipDisplayValue(chip: FilterChip): string {
  if (chip.field === "duplicate_state") return DUPLICATE_STATE_LABELS[chip.value] || chip.value;
  return chip.value;
}

export function getAttrFieldType(attr: AttributeField): FieldType {
  if (attr.enum_choices?.length) {
    // Array attributes with choices → multi-select; scalar attributes → single-select
    return attr.field_type === "array" ? "enum" : "enum_single";
  }
  switch (attr.field_type) {
    case "number":
    case "integer":
      return "numeric";
    case "boolean":
      return "boolean";
    default:
      return "string";
  }
}
