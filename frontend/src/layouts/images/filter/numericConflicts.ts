import { FilterChip } from "../../../context/ImageListDataContext";
import { NUMERIC_FIELDS, DATE_FIELDS } from "../../../context/filterUtils";

/**
 * Slot-based conflict resolution for numeric filter chips.
 *
 * Operators are grouped into slots that replace within their slot
 * but coexist across slots:
 *   Lower bound: gt, gte  — coexists with upper bound
 *   Upper bound: lt, lte  — coexists with lower bound
 *   Exact:       eq       — replaces everything (exact match)
 *   Existence:   exists, not_exists — replaces everything
 *   Exclusion:   ne       — additive, only removes exists/not_exists
 */

const LOWER = new Set(["gt", "gte"]);
const UPPER = new Set(["lt", "lte"]);

/** Operators replaced by a histogram range commit (everything except !=). */
export const RANGE_REPLACES = new Set(["eq", "gt", "gte", "lt", "lte", "exists", "not_exists"]);

/** Return chip IDs that conflict with a new operator on a numeric field. */
export function getNumericConflicts(chips: FilterChip[], field: string, newOp: string): string[] {
  if (!NUMERIC_FIELDS.has(field) && !DATE_FIELDS.has(field)) return [];
  return chips
    .filter(c => {
      if (c.field !== field) return false;
      if (newOp === "ne") {
        return c.operator === "exists" || c.operator === "not_exists";
      }
      if (newOp === "eq" || newOp === "exists" || newOp === "not_exists") {
        return c.operator !== "ne";
      }
      if (LOWER.has(newOp)) {
        return LOWER.has(c.operator) || c.operator === "eq" || c.operator === "exists" || c.operator === "not_exists";
      }
      if (UPPER.has(newOp)) {
        return UPPER.has(c.operator) || c.operator === "eq" || c.operator === "exists" || c.operator === "not_exists";
      }
      return false;
    })
    .map(c => c.id);
}

/** Parse typed range input like "500-600", "500:600", "500,600", "500 to 600". */
export function parseRangeInput(text: string): [number, number] | null {
  const trimmed = text.trim();
  if (!trimmed) return null;
  for (const sep of [" to ", ":", ",", "-"]) {
    // For "-", skip a leading minus sign (negative number)
    const idx = sep === "-" ? trimmed.indexOf(sep, 1) : trimmed.indexOf(sep);
    if (idx > 0 && idx < trimmed.length - sep.length) {
      const a = Number(trimmed.slice(0, idx).trim());
      const b = Number(trimmed.slice(idx + sep.length).trim());
      if (!isNaN(a) && !isNaN(b)) return [Math.min(a, b), Math.max(a, b)];
    }
  }
  return null;
}

/** ISO date pattern YYYY-MM-DD */
const ISO_DATE = /^\d{4}-\d{2}-\d{2}$/;

/** Parse typed date range input. Supports:
 *  - "2024-01-01 to 2024-06-30"
 *  - "2024-01-01 2024-06-30"  (space-separated)
 *  - "2024-01-01"             (single date → both start and end)
 */
export function parseDateRangeInput(text: string): [string, string] | null {
  const trimmed = text.trim();
  if (!trimmed) return null;

  // Try " to " separator first
  for (const sep of [" to ", "  ", " "]) {
    const idx = trimmed.indexOf(sep);
    if (idx > 0) {
      const a = trimmed.slice(0, idx).trim();
      const b = trimmed.slice(idx + sep.length).trim();
      if (ISO_DATE.test(a) && ISO_DATE.test(b)) {
        return a <= b ? [a, b] : [b, a];
      }
    }
  }

  // Single date
  if (ISO_DATE.test(trimmed)) {
    return [trimmed, trimmed];
  }

  return null;
}

/** Compute a rounded range example string for a histogram hint. */
export function computeRangeExample(min: number, max: number): string {
  const magnitude = 10 ** Math.floor(Math.log10(Math.abs(max) || 1));
  const step = Math.max(1, Math.round(magnitude * 0.1));
  const roundTo = (n: number) => Math.round(n / step) * step;
  const span = max - min;
  return `${roundTo(min + span * 0.25)}-${roundTo(max - span * 0.25)}`;
}
