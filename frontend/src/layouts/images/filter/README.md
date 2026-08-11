# Filter Bar System

The filter bar provides a guided, multi-stage autocomplete for building image
filters. It supports keyword fields (source, tag, dataset), numeric fields with
histogram sliders, custom attributes, similarity search, and advanced OR/NOT
filter logic.

## Architecture

```
SearchFilterBar.tsx              ← UI: compact bar, chips overlay, dropdown mount
  ├─ useSearchFilterBar.ts       ← orchestrator hook (state, keyboard, refs, lanes)
  │    ├─ useDropdownSections.ts ← builds dropdown items per stage
  │    ├─ useNumericHistogram.ts ← histogram state & commit logic
  │    ├─ numericConflicts.ts    ← pure functions: conflict resolution, range parsing
  │    └─ useFacets.ts           ← fetches GET /api/images/facets/ (self-exclusion)
  ├─ FilterDropdown.tsx          ← dropdown: sections, checkboxes, histogram, status bar
  ├─ FilterChip.tsx              ← chip display variants (single, grouped, numeric)
  ├─ Histogram.tsx               ← bar chart + range/single slider
  ├─ AdvancedFilterDialog.tsx    ← portal dialog for OR groups / NOT toggle
  └─ constants.ts                ← types, field/operator definitions, helpers

ImageListDataContext.tsx          ← lane state, committed params, count query
filterUtils.ts                   ← lane ↔ API param conversion, URL parsing
```

## Data Model: Lanes

Filters are organized into **lanes** (called "groups" in the UI). Each lane
contains a list of filter chips that are AND'd together. Lanes are OR'd:

```
(lane1.chip1 AND lane1.chip2) OR (lane2.chip1) OR NOT(lane3.chip1)
```

```typescript
interface FilterLane {
  id: string;
  chips: FilterChip[];
  negated: boolean; // wraps this lane's query in must_not
}
```

A single non-negated lane is backward compatible with flat query params. Multiple
lanes or any negated lane serialize as `?filter_lanes=<JSON>`.

## Three-Stage Flow

The filter bar walks the user through three stages:

1. **Field** — pick what to filter on (source, width, attr:quality, etc.)
2. **Operator** — pick how to compare (=, !=, >, >=, ~range, etc.)
3. **Value** — pick or type the filter value

Each stage shows a dropdown with contextual suggestions. Selection advances
to the next stage. Keyboard shortcuts allow skipping (e.g. typing `source:dev`
creates an `eq` chip in one step).

## Field Types

| Type          | Example fields                         | Operators                          | Stage 3 UI                                   |
| ------------- | -------------------------------------- | ---------------------------------- | -------------------------------------------- |
| `multi`       | source, tag, dataset                   | =, !=                              | Multi-select checkboxes with filtered counts |
| `enum`        | array attributes with choices          | =, !=                              | Multi-select checkboxes                      |
| `enum_single` | scalar attributes with choices         | =, !=                              | Single-select dropdown (no checkboxes)       |
| `numeric`     | width, height, pixel_count             | ~range, =, !=, >, >=, <, <=, ?, !? | Histogram with slider                        |
| `string`      | aspect_ratio_fraction, text attributes | =, !=, ~, ^, ?, !?                 | Text input                                   |
| `boolean`     | boolean attributes                     | =, !=, ?, !?                       | true/false list                              |
| `date`        | date_created, date_updated             | >, >=, <, <=                       | Text input                                   |

`enum` vs `enum_single`: attributes with `enum_choices` use multi-select if
`field_type === "array"` (can hold multiple values), single-select otherwise
(e.g. "license" — an image can only have one).

## Compact Bar & Overlay

The filter bar is always single-line height (`h-[2.25rem]`, `overflow-hidden`):

- **Desktop (inactive)**: shows first 3 chip groups inline + "+N more" overflow
- **Mobile (inactive)**: shows "N filters" badge
- **Active (focused/editing)**: chips move to a floating overlay panel below the bar,
  with the dropdown directly beneath. Both are in a single absolute container so
  they stack without overlapping.

The dropdown includes a **status bar** (sticky top) showing:

- Left: image count ("12,345 images found") from `/api/images/count/`
- Right: "Advanced" link to open the advanced filter dialog

A **Done/Apply button** (sticky bottom) is always visible for closing/applying.

## Multi-Select (keyword fields)

Fields like source, tag, and dataset use multi-select dropdowns:

- Checkboxes in the dropdown; clicking toggles without closing
- Same-field same-operator chips group visually: `Source = a, b +1 more`
- Enter/Escape closes the dropdown
- Counts come from the facets endpoint and reflect all other active filters

## Numeric Fields & Histograms

Numeric fields have a special `~range` virtual operator (first in the list)
plus the standard comparison operators.

### Range mode (`~range` operator)

- Shows histogram with **two slider handles** (lower + upper bound)
- Commits as `gte` + `lte` chips
- User can also type `500-1000`, `500:1000`, `500,1000`, or `500 to 1000`
- Replaces all existing non-`!=` chips for the field

### Single-value mode (`=`, `>`, `>=`, `<`, `<=`)

- Shows histogram with **one slider handle**
- Commits as the selected operator + value
- User can also type a value directly

### Deferred application

All filter edits are **deferred** — they update draft state (`lanes`) but the
browse query, count query, and URL only update when committed:

- Enter, Tab, or Escape is pressed
- The "Apply" / "Done" button is clicked
- The user clicks outside the dropdown

This applies to all filter types. Multi-select toggles (`addChip` / `removeChipDraft`)
only update draft lanes. Direct chip removals via X buttons commit immediately.
The context maintains `lanes` (draft) and `committedLanes` (what the API uses).

## Apply / Done Button

A full-width button is always visible at the bottom of the dropdown:

- **"Apply"** (when a field is selected): commits the current filter and closes
- **"Done"** (when no field is selected): closes the dropdown

For histograms, Apply commits the slider range as chips. For everything else,
it finalizes the current filter stage and closes. On mobile this is the primary
way to dismiss the dropdown.

## Numeric Conflict Resolution (slot-based)

When adding a new filter to a numeric field, existing filters are
cleaned up based on operator slots:

| Slot        | Operators | Coexists with            |
| ----------- | --------- | ------------------------ |
| Lower bound | `>`, `>=` | Upper bound              |
| Upper bound | `<`, `<=` | Lower bound              |
| Exact       | `=`       | (replaces all except !=) |
| Existence   | `?`, `!?` | (replaces all except !=) |
| Exclusion   | `!=`      | Everything               |

Examples:

- `width > 500` then `width < 1000` → `Width: >500, <1000` (coexist)
- `width > 500` then `width >= 600` → `Width: >=600` (same slot, replaced)
- `width > 500, < 1000` then `width = 800` → `Width: =800` (exact replaces all)
- `width > 500` then `width != 700` → `Width: >500` + `Width !=700` (additive)
- Histogram range → replaces all except `!=`

Combined numeric chips display as `Width: >=500, <=1000`. The `!=` chips
always render separately.

## Faceted Search

The dropdown counts reflect the **currently active filters** (true faceted
search). This is powered by `GET /api/images/facets/`:

- Accepts `fields=source,tag,width` to aggregate multiple fields in one query
- Accepts `exclude_field=source` for self-exclusion (so source counts aren't
  filtered by the active source filter)
- The frontend sends all active filter params except those for the field being
  faceted, via `chipsToApiParamsExcluding()`

### Self-exclusion prevents stale counts

Facet params always exclude the field being edited (`chipsToApiParamsExcluding`).
This means toggling values in a multi-select (which adds/removes chips for the
selected field) does **not** change the facet query params — counts stay stable.
But removing a chip for a _different_ field (e.g. removing a tag chip while
editing source) correctly triggers a facet refetch with updated counts.

The facets endpoint returns:

- **Terms fields**: `{ buckets: [{ key, doc_count }] }` — used for keyword/enum dropdowns
- **Numeric fields**: `{ stats: { min, max, count, avg }, histogram: [{ key, doc_count }] }` — used for histograms

The only exception is `latent` which can't be aggregated in OpenSearch
(latent types are stored as separate dynamic fields) and falls back to
`/api/stats/latent_types/`.

## Image Count

The total matching image count is fetched from `GET /api/images/count/` using
the same filter params as the browse query. It's displayed in the dropdown's
sticky status bar as "N images found".

## Advanced Filters (OR Groups / Negate)

Accessible via the "Advanced" link in the dropdown status bar. Opens a portal
dialog (`AdvancedFilterDialog.tsx`) where users can:

- **Add OR groups**: each group is a set of AND'd filters, groups are OR'd
- **Negate groups**: wraps a group in `must_not` (includes the complement)
- **Edit across groups**: clicking a chip in a non-active group switches focus

### Backend: multi-lane filter

When multiple lanes or negated lanes are active, the frontend sends
`?filter_lanes=<JSON>` instead of flat params. The backend
(`OSFilterBackend.filter_search_lanes`) processes each lane through the
existing `OSImageFilterSet`, extracts the query, and combines with
`bool.should` (OR) + `must_not` for negated lanes.

### Limitations

- **Similarity search is hidden** in advanced mode because KNN queries can't
  be combined with `bool.should` in OpenSearch.
- **New OR groups** can only be added when the current active group has at
  least one filter chip.

## Chip Display Variants

| Variant                      | Used for                 | Example                         |
| ---------------------------- | ------------------------ | ------------------------------- |
| `ChipDisplay`                | Single filters           | `Source = dev`                  |
| `GroupedChipDisplay`         | Multi-select groups      | `Tag = nature, outdoor +1 more` |
| `CombinedNumericChipDisplay` | Numeric range combos     | `Width >=500, <=1000`           |
| `SimilarityChip`             | Active similarity search | `Text: sunset over ocean`       |

## Similarity Search

Three modes, accessible from the field dropdown (simple mode only):

- **Text Search** — type a description, press Enter
- **Image Search** — upload an image file
- **Vector Search** — paste a 768-dim embedding vector

Activating similarity search clears all filter lanes.

## Keyboard Shortcuts

| Key                   | Stage 1                         | Stage 2               | Stage 3                                    |
| --------------------- | ------------------------------- | --------------------- | ------------------------------------------ |
| Enter                 | Text search (if no field match) | Select highlighted op | Commit value / apply slider                |
| Tab                   | —                               | Select highlighted op | Commit value / apply slider                |
| Escape                | Close dropdown                  | Back to stage 1       | Commit slider / close                      |
| Backspace (empty)     | Remove last chip                | Back to stage 1       | Close (multi/histogram) or back to stage 2 |
| `=`, `!=`, `>=`, `<=` | —                               | Auto-select operator  | —                                          |
| `>`, `<`              | —                               | Select on Enter       | —                                          |
| `field:value`         | Quick filter shortcut           | —                     | —                                          |

## URL Persistence

- **Single non-negated lane**: flat query params (backward compatible)
  `?sources=a,b&width__gte=500`
- **Multi-lane or negated**: JSON param
  `?filter_lanes=[{"chips":[...],"negated":false},...]`
- Parsed on mount via `parseLanesFromUrl()`, synced on change via
  `lanesToAllFilterParamKeys()` + `lanesToApiParams()`

## File Responsibilities

| File                       | Purpose                                                     |
| -------------------------- | ----------------------------------------------------------- |
| `constants.ts`             | Types, field/operator definitions, display helpers          |
| `useSearchFilterBar.ts`    | Orchestrator: state, keyboard, refs, chip editing, lanes    |
| `useDropdownSections.ts`   | Builds dropdown content for each stage                      |
| `useNumericHistogram.ts`   | Histogram state, init, commit (range & single)              |
| `numericConflicts.ts`      | Pure functions: conflict resolution, range parsing          |
| `useFacets.ts`             | React Query hook for `/api/images/facets/` (self-exclusion) |
| `FilterDropdown.tsx`       | Dropdown UI: status bar, sections, checkboxes, histogram    |
| `Histogram.tsx`            | Bar chart + dual/single range slider                        |
| `FilterChip.tsx`           | Chip display components                                     |
| `AdvancedFilterDialog.tsx` | Portal dialog for OR groups and negate toggle               |
| `SearchFilterBar.tsx`      | Top-level: compact bar, chips overlay, dropdown             |
| `ImageListDataContext.tsx` | Lane state, filter params, count query, URL sync            |
| `filterUtils.ts`           | Lane <-> API param conversion, URL parsing utilities        |
