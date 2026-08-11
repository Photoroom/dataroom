import { FilterChip, FilterLane } from "./ImageListDataContext";

// -------------------- Constants --------------------

export const NUMERIC_FIELDS = new Set(["width", "height", "short_edge", "pixel_count", "aspect_ratio"]);
export const DATE_FIELDS = new Set(["date_created", "date_updated"]);

let _chipId = 0;
export const genChipId = () => `c${_chipId++}`;

let _laneId = 0;
export const genLaneId = () => `l${_laneId++}`;

export function createEmptyLane(): FilterLane {
  return { id: genLaneId(), chips: [], negated: false };
}

// -------------------- Pure functions --------------------

export function chipsToApiParamsExcluding(chips: FilterChip[], excludeField: string): Record<string, string> {
  return chipsToApiParams(chips.filter(c => c.field !== excludeField));
}

export function chipsToApiParams(chips: FilterChip[]): Record<string, string> {
  const params: Record<string, string> = {};

  // Group chips by field
  const byField = new Map<string, FilterChip[]>();
  for (const chip of chips) {
    const arr = byField.get(chip.field) || [];
    arr.push(chip);
    byField.set(chip.field, arr);
  }

  for (const [field, fieldChips] of byField) {
    if (field === "source") {
      const eq = fieldChips.filter(c => c.operator === "eq").map(c => c.value);
      const ne = fieldChips.filter(c => c.operator === "ne").map(c => c.value);
      if (eq.length) params.sources = eq.join(",");
      if (ne.length) params.sources__ne = ne.join(",");
    } else if (field === "tag") {
      const eq = fieldChips.filter(c => c.operator === "eq").map(c => c.value);
      const ne = fieldChips.filter(c => c.operator === "ne").map(c => c.value);
      if (eq.length) params.tags = eq.join(",");
      if (ne.length) params.tags__ne = ne.join(",");
    } else if (field === "dataset") {
      const eq = fieldChips.filter(c => c.operator === "eq").map(c => c.value);
      const ne = fieldChips.filter(c => c.operator === "ne").map(c => c.value);
      const prefixVals = fieldChips.filter(c => c.operator === "prefix").map(c => c.value);
      if (eq.length) params.datasets = eq.join(",");
      if (ne.length) params.datasets__ne = ne.join(",");
      if (prefixVals.length) params.datasets__prefix = prefixVals.join(",");
    } else if (field === "latent") {
      const eq = fieldChips.filter(c => c.operator === "eq").map(c => c.value);
      const ne = fieldChips.filter(c => c.operator === "ne").map(c => c.value);
      if (eq.length) params.has_latents = eq.join(",");
      if (ne.length) params.lacks_latents = ne.join(",");
    } else if (field === "group") {
      const eq = fieldChips.filter(c => c.operator === "eq").map(c => c.value);
      if (eq.length) params.group_ids = eq.join(",");
    } else if (field === "group_type") {
      params.group_type = fieldChips[0].value;
    } else if (field === "role") {
      const eq = fieldChips.filter(c => c.operator === "eq").map(c => c.value);
      if (eq.length) params.roles = eq.join(",");
    } else if (field === "duplicate_state") {
      params.duplicate_state = fieldChips[0].value;
    } else if (field === "aspect_ratio_fraction") {
      params.aspect_ratio_fraction = fieldChips[0].value;
    } else if (NUMERIC_FIELDS.has(field)) {
      for (const chip of fieldChips) {
        if (chip.operator === "eq") params[field] = chip.value;
        else params[`${field}__${chip.operator}`] = chip.value;
      }
    } else if (DATE_FIELDS.has(field)) {
      for (const chip of fieldChips) {
        params[`${field}__${chip.operator}`] = chip.value;
      }
    } else if (field.startsWith("attr:")) {
      const attrName = field.slice(5);
      const existsChips = fieldChips.filter(c => c.operator === "exists");
      const notExistsChips = fieldChips.filter(c => c.operator === "not_exists");
      const valueChips = fieldChips.filter(c => c.operator !== "exists" && c.operator !== "not_exists");

      if (existsChips.length) {
        const existing = params.has_attributes ? params.has_attributes.split(",") : [];
        existing.push(attrName);
        params.has_attributes = existing.join(",");
      }
      if (notExistsChips.length) {
        const existing = params.lacks_attributes ? params.lacks_attributes.split(",") : [];
        existing.push(attrName);
        params.lacks_attributes = existing.join(",");
      }
      if (valueChips.length) {
        const parts: string[] = params.attributes ? params.attributes.split(",") : [];
        for (const chip of valueChips) {
          if (chip.operator === "eq") parts.push(`${attrName}:${chip.value}`);
          else parts.push(`${attrName}__${chip.operator}:${chip.value}`);
        }
        params.attributes = parts.join(",");
      }
    } else if (field === "has_attributes") {
      params.has_attributes = fieldChips.map(c => c.value).join(",");
    } else if (field === "lacks_attributes") {
      params.lacks_attributes = fieldChips.map(c => c.value).join(",");
    }
  }
  return params;
}

export function parseChipsFromUrl(sp: URLSearchParams): FilterChip[] {
  const chips: FilterChip[] = [];
  const add = (field: string, operator: string, value: string) =>
    chips.push({ id: genChipId(), field, operator, value });

  // Multi-value fields
  const csv = (key: string) => sp.get(key)?.split(",").filter(Boolean) || [];

  for (const v of csv("sources")) add("source", "eq", v);
  for (const v of csv("sources__ne")) add("source", "ne", v);
  for (const v of csv("tags")) add("tag", "eq", v);
  for (const v of csv("tags__ne")) add("tag", "ne", v);
  for (const v of csv("datasets")) add("dataset", "eq", v);
  for (const v of csv("datasets__ne")) add("dataset", "ne", v);
  for (const v of csv("datasets__prefix")) add("dataset", "prefix", v);
  for (const v of csv("has_latents")) add("latent", "eq", v);
  for (const v of csv("lacks_latents")) add("latent", "ne", v);
  for (const v of csv("group_ids")) add("group", "eq", v);
  for (const v of csv("roles")) add("role", "eq", v);
  const gt = sp.get("group_type");
  if (gt) add("group_type", "eq", gt);
  for (const v of csv("has_attributes")) add("has_attributes", "eq", v);
  for (const v of csv("lacks_attributes")) add("lacks_attributes", "eq", v);

  // Single-value fields
  const ds = sp.get("duplicate_state");
  if (ds) add("duplicate_state", "eq", ds);
  const arf = sp.get("aspect_ratio_fraction");
  if (arf) add("aspect_ratio_fraction", "eq", arf);

  // Attributes (name:value or name__op:value)
  const attrs = sp.get("attributes");
  if (attrs) {
    for (const pair of attrs.split(",")) {
      const colonIdx = pair.indexOf(":");
      if (colonIdx <= 0) continue;
      let attrName = pair.slice(0, colonIdx);
      const attrValue = pair.slice(colonIdx + 1);
      let op = "eq";
      const dunderIdx = attrName.indexOf("__");
      if (dunderIdx > 0) {
        op = attrName.slice(dunderIdx + 2);
        attrName = attrName.slice(0, dunderIdx);
      }
      add(`attr:${attrName}`, op, attrValue);
    }
  }

  // Numeric fields (exact + range)
  for (const field of NUMERIC_FIELDS) {
    const exact = sp.get(field);
    if (exact) add(field, "eq", exact);
    for (const op of ["gt", "gte", "lt", "lte", "ne"]) {
      const val = sp.get(`${field}__${op}`);
      if (val) add(field, op, val);
    }
  }

  // Date fields (range only)
  for (const field of DATE_FIELDS) {
    for (const op of ["gt", "gte", "lt", "lte"]) {
      const val = sp.get(`${field}__${op}`);
      if (val) add(field, op, val);
    }
  }

  return chips;
}

export function getAllFilterParamKeys(chips: FilterChip[]): string[] {
  const keys = new Set<string>();
  // Static keys
  for (const k of [
    "sources",
    "sources__ne",
    "tags",
    "tags__ne",
    "datasets",
    "datasets__ne",
    "datasets__prefix",
    "has_latents",
    "lacks_latents",
    "group_ids",
    "roles",
    "group_type",
    "has_attributes",
    "lacks_attributes",
    "duplicate_state",
    "aspect_ratio_fraction",
    "attributes",
    "filter_lanes",
  ])
    keys.add(k);

  // Numeric/date keys
  for (const field of [...NUMERIC_FIELDS, ...DATE_FIELDS]) {
    keys.add(field);
    for (const op of ["gt", "gte", "lt", "lte", "ne"]) {
      keys.add(`${field}__${op}`);
    }
  }

  // Keys from current chips (in case of extra params)
  for (const [k] of Object.entries(chipsToApiParams(chips))) {
    keys.add(k);
  }

  return [...keys];
}

// -------------------- Lane functions --------------------

export function isAdvancedFilter(lanes: FilterLane[]): boolean {
  return lanes.length > 1 || lanes.some(l => l.negated);
}

export function lanesToApiParams(lanes: FilterLane[]): Record<string, string> {
  // Single non-negated lane: backward compatible flat params
  if (lanes.length === 1 && !lanes[0].negated) {
    return chipsToApiParams(lanes[0].chips);
  }
  // Multi-lane or negated: serialize as JSON
  const serialized = lanes.map(lane => ({
    chips: lane.chips.map(c => ({ field: c.field, operator: c.operator, value: c.value })),
    negated: lane.negated,
  }));
  return { filter_lanes: JSON.stringify(serialized) };
}

export function lanesToAllFilterParamKeys(lanes: FilterLane[]): string[] {
  // Collect keys from all lanes' chips, plus the filter_lanes key
  const allChips = lanes.flatMap(l => l.chips);
  return getAllFilterParamKeys(allChips);
}

export function parseLanesFromUrl(sp: URLSearchParams): FilterLane[] {
  // Check for multi-lane JSON param first
  const lanesJson = sp.get("filter_lanes");
  if (lanesJson) {
    try {
      const parsed = JSON.parse(lanesJson) as { chips: Omit<FilterChip, "id">[]; negated: boolean }[];
      return parsed.map(lane => ({
        id: genLaneId(),
        chips: lane.chips.map(c => ({ ...c, id: genChipId() })),
        negated: lane.negated,
      }));
    } catch {
      // Fall through to flat param parsing
    }
  }
  // Fallback: parse flat params into a single lane
  const chips = parseChipsFromUrl(sp);
  return [{ id: genLaneId(), chips, negated: false }];
}
