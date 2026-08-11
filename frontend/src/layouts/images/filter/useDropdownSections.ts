import { useMemo } from "react";
import {
  FieldType,
  DropdownSection,
  DropdownItem,
  BUILTIN_FIELDS,
  OPERATORS_BY_TYPE,
  SIMILARITY_FIELDS,
  SHOW_MORE_KEY,
  getFieldLabel,
  isCatalogField,
} from "./constants";
import { computeRangeExample } from "./numericConflicts";
import type { FacetBucket } from "./useFacets";
import type { AttributeField, Group, GroupType, Query, Role } from "../../../api/client.schemas";
import type React from "react";
import { BookmarkIcon } from "@heroicons/react/20/solid";
import { MyQueryIcon } from "./MyQueryIcon";

interface UseDropdownSectionsArgs {
  stage: 1 | 2 | 3;
  inputValue: string;
  selectedField: string | null;
  selectedFieldType: FieldType | null;
  selectedOperator: string | null;
  indexedAttrs: AttributeField[];
  simMode: "text" | "image" | "vector" | null;
  isRangeOp: boolean;
  isSingleNumericOp: boolean;
  facetBuckets: FacetBucket[];
  facetStats: { min: number; max: number } | null;
  /**
   * Full, client-cached value set for catalog fields (source, tag, dataset, keyword attrs).
   * Counts are filter-aware when filters on other fields are active, global otherwise.
   */
  catalogValues: FacetBucket[];
  /** How many values to show before the "Show more" row (stage-3 value lists). */
  valueLimit: number;
  latentsData: { name: string; image_count: number }[] | undefined;
  groupsData: Group[];
  rolesData: Role[];
  groupTypesData: GroupType[];
  queriesData: Query[];
  /** Slug of the currently bound saved query, marked as selected in the list. */
  activeQuerySlug: string | null;
  /** Email of the logged-in user — their own saved queries are emphasized in the list. */
  currentUserEmail?: string;
  similarityIcons: Record<string, React.ComponentType<{ className?: string }>>;
  /** Hide similarity search options (e.g. in advanced filter mode where KNN can't be OR'd) */
  hideSimilarity?: boolean;
}

export function useDropdownSections({
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
  catalogValues,
  valueLimit,
  latentsData,
  groupsData,
  rolesData,
  groupTypesData,
  queriesData,
  activeQuerySlug,
  currentUserEmail,
  similarityIcons,
  hideSimilarity,
}: UseDropdownSectionsArgs) {
  const rangeExample = useMemo(() => {
    if (!facetStats || !isRangeOp) return "";
    return computeRangeExample(facetStats.min, facetStats.max);
  }, [facetStats, isRangeOp]);

  const dropdownSections = useMemo((): DropdownSection[] => {
    if (simMode) return [];

    // Stage 1: Field selection
    if (stage === 1) {
      const query = inputValue.toLowerCase();
      const matches = (f: { key: string; label: string }) =>
        !query || f.key.toLowerCase().includes(query) || f.label.toLowerCase().includes(query);

      const categories = new Map<string, DropdownItem[]>();
      for (const f of BUILTIN_FIELDS) {
        if (!matches(f)) continue;
        const items = categories.get(f.category) || [];
        items.push({ key: f.key, label: f.label, typeBadge: f.typeBadge });
        categories.set(f.category, items);
      }

      const attrItems: DropdownItem[] = [];
      for (const attr of indexedAttrs) {
        if (
          !query ||
          attr.name.toLowerCase().includes(query) ||
          (attr.description || "").toLowerCase().includes(query)
        ) {
          attrItems.push({
            key: `attr:${attr.name}`,
            label: attr.name,
            description: attr.description,
            typeBadge: attr.field_type || "string",
            count: attr.image_count,
          });
        }
      }

      const simItems: DropdownItem[] = [];
      for (const sf of SIMILARITY_FIELDS) {
        if (!query || sf.label.toLowerCase().includes(query) || sf.key.toLowerCase().includes(query)) {
          simItems.push({
            key: sf.key,
            label: sf.label,
            description: sf.description,
            icon: similarityIcons[sf.iconName],
          });
        }
      }

      // Saved queries: clicking one loads its stored filters as editable chips (keyed "query:<slug>").
      const queryItems: DropdownItem[] = [];
      for (const q of queriesData) {
        if (!query || q.name.toLowerCase().includes(query) || q.slug.toLowerCase().includes(query)) {
          const isMine = !!currentUserEmail && q.author?.email === currentUserEmail;
          queryItems.push({
            key: `query:${q.slug}`,
            label: q.name,
            description: q.description || undefined,
            // Your own queries get a starred bookmark; everyone else's get a plain bookmark.
            icon: isMine ? MyQueryIcon : BookmarkIcon,
            // Mark the currently-loaded query so it's clear which one is selected.
            rightLabel: q.slug === activeQuerySlug ? "selected" : undefined,
            // Emphasize the user's own queries so they stand out from others'.
            emphasized: isMine,
          });
        }
      }

      const sections: DropdownSection[] = [];
      if (queryItems.length) sections.push({ header: "Saved Queries", items: queryItems });
      for (const [header, items] of categories) {
        if (items.length) sections.push({ header, items });
      }
      attrItems.sort((a, b) => (b.count ?? 0) - (a.count ?? 0));
      if (attrItems.length) sections.push({ header: "Attributes", items: attrItems });
      if (simItems.length && !hideSimilarity) sections.push({ header: "Similarity Search", items: simItems });
      return sections;
    }

    // Stage 2: Operator selection
    if (stage === 2) {
      const ops = selectedFieldType ? OPERATORS_BY_TYPE[selectedFieldType] || [] : [];
      const query = inputValue.toLowerCase();
      const filtered = ops.filter(o => !query || o.symbol.includes(query) || o.label.toLowerCase().includes(query));
      return [
        {
          header: `Operator for ${getFieldLabel(selectedField!)}`,
          items: filtered.map(o => ({ key: o.key, label: o.symbol, rightLabel: o.label })),
        },
      ];
    }

    // Stage 3: Value suggestions

    // Free-text operators (match, prefix, not_match, not_match_phrase, not_prefix):
    // don't show value suggestions — the user is typing a search term, not picking from a list
    const FREE_TEXT_OPS = new Set(["match", "match_phrase", "prefix", "not_match", "not_match_phrase", "not_prefix"]);
    if (selectedOperator && FREE_TEXT_OPS.has(selectedOperator)) {
      return [{ header: "Type a value and press Enter", items: [] }];
    }

    const items: DropdownItem[] = [];
    const query = inputValue.toLowerCase();
    const hasFacetBuckets = facetBuckets.length > 0;

    if (selectedField === "duplicate_state") {
      const options = [
        { value: "None", label: "Unprocessed" },
        { value: "1", label: "Original" },
        { value: "2", label: "Duplicate" },
      ];
      for (const opt of options) {
        if (!query || opt.label.toLowerCase().includes(query) || opt.value.includes(query)) {
          const bucket = facetBuckets.find(b => String(b.key) === opt.value);
          items.push({ key: opt.value, label: opt.label, count: bucket?.doc_count });
        }
      }
    } else if (selectedField === "latent") {
      for (const l of latentsData || []) {
        if (!query || l.name.toLowerCase().includes(query)) {
          items.push({ key: l.name, label: l.name, count: l.image_count });
        }
      }
    } else if (selectedField === "group") {
      for (const g of groupsData) {
        const haystack = `${g.name} ${g.type} ${g.id}`.toLowerCase();
        if (!query || haystack.includes(query)) {
          items.push({ key: g.id, label: g.name, rightLabel: g.type, count: g.image_count });
        }
      }
    } else if (selectedField === "role") {
      for (const r of rolesData) {
        if (!query || r.name.toLowerCase().includes(query)) {
          items.push({ key: r.name, label: r.name, description: r.description ?? undefined });
        }
      }
    } else if (selectedField === "group_type") {
      for (const gt of groupTypesData) {
        if (!query || gt.name.toLowerCase().includes(query)) {
          items.push({ key: gt.name, label: gt.name, description: gt.description ?? undefined });
        }
      }
    } else if (isCatalogField(selectedField ?? "", selectedFieldType ?? undefined)) {
      // Unbounded fields: filter the full client-cached catalog locally (no per-keystroke fetch).
      for (const b of catalogValues) {
        const key = String(b.key);
        if (!query || key.toLowerCase().includes(query)) {
          items.push({ key, label: key, count: b.doc_count });
        }
      }
    } else if (hasFacetBuckets) {
      // Boolean attributes: OpenSearch returns 1/0 as bucket keys.
      // Map to true/false for display and filter value.
      const isBooleanAttr =
        selectedField?.startsWith("attr:") &&
        indexedAttrs.find(a => a.name === selectedField.slice(5))?.field_type === "boolean";
      for (const bucket of facetBuckets) {
        const rawKey = String(bucket.key);
        const key = isBooleanAttr ? (rawKey === "1" ? "true" : rawKey === "0" ? "false" : rawKey) : rawKey;
        const label = key;
        if (!query || label.toLowerCase().includes(query)) {
          items.push({ key, label, count: bucket.doc_count });
        }
      }
    } else if (selectedField?.startsWith("attr:")) {
      const attrName = selectedField.slice(5);
      const attr = indexedAttrs.find(a => a.name === attrName);
      const choices = (attr?.enum_choices as unknown as unknown[] | null | undefined) ?? [];
      if (choices.length) {
        for (const choice of choices) {
          if (!query || String(choice).toLowerCase().includes(query)) {
            items.push({ key: String(choice), label: String(choice) });
          }
        }
      } else if (attr?.field_type === "boolean") {
        for (const v of ["true", "false"]) {
          if (!query || v.includes(query)) items.push({ key: v, label: v });
        }
      }
    }

    // Date range hint
    if (selectedFieldType === "date") {
      return [{ header: "Pick a range below or type e.g. 2024-01-01 to 2024-12-31", items: [] }];
    }

    // Numeric histogram hint
    if (selectedFieldType === "numeric" && (isRangeOp || isSingleNumericOp)) {
      if (!facetStats) {
        return [{ header: "No values found for this field", items: [] }];
      }
      if (isRangeOp) {
        return [{ header: `Type a range, e.g. ${rangeExample}`, items: [] }];
      }
      return [{ header: "Type a value or use the slider", items: [] }];
    }

    if (items.length === 0) {
      return [{ header: "Type a value and press Enter", items: [] }];
    }
    items.sort((a, b) => (b.count ?? 0) - (a.count ?? 0));

    // Paginate locally: show `valueLimit` values, then a "Show more" row to reveal the rest.
    const limited = valueLimit > 0 ? items.slice(0, valueLimit) : items;
    if (limited.length < items.length) {
      limited.push({ key: SHOW_MORE_KEY, label: "Show more", isShowMore: true });
    }
    return [{ header: "Values", items: limited }];
  }, [
    stage,
    inputValue,
    selectedField,
    selectedFieldType,
    indexedAttrs,
    latentsData,
    queriesData,
    activeQuerySlug,
    currentUserEmail,
    simMode,
    facetBuckets,
    facetStats,
    catalogValues,
    valueLimit,
    isRangeOp,
    isSingleNumericOp,
    selectedOperator,
    rangeExample,
    similarityIcons,
    hideSimilarity,
  ]);

  return { dropdownSections, rangeExample };
}
