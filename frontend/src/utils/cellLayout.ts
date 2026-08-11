// Grid classes for splitting a square tile into N cells (role thumbnails on
// the dataset page, dataset cover collages) — literal strings so Tailwind
// sees them.
const GRID_COLS: Record<number, string> = { 1: "grid-cols-1", 2: "grid-cols-2", 3: "grid-cols-3" };
const GRID_SPAN: Record<number, string> = { 2: "col-span-2", 3: "col-span-3" };

/** Column count + last-cell span so N cells always fill the grid rectangle. */
export function cellLayout(count: number) {
  const cols = count <= 1 ? 1 : count <= 4 ? 2 : 3;
  const lastSpan = cols - ((count - 1) % cols);
  return { colsClass: GRID_COLS[cols], lastSpanClass: lastSpan > 1 ? GRID_SPAN[lastSpan] : "" };
}
