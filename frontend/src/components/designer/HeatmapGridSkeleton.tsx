/**
 * Loading placeholder for {@link AffectHeatmapGrid} (Story 7.3, AC5).
 *
 * Mirrors the 7.2 skeleton discipline (animate-pulse + bg-border blocks,
 * role="status"). Shapes a header row + several section rows × 4 cells so the
 * grid does not reflow on load. NOT a spinner — skeletons are an explicit AC.
 */

const GRID_TEMPLATE = "minmax(10rem,2fr) repeat(4, minmax(4.5rem, 1fr))";
const ROWS = 6;

export function HeatmapGridSkeleton() {
  return (
    <div
      role="status"
      aria-label="Loading affect heatmap"
      className="animate-pulse overflow-hidden rounded-xl border border-border bg-surface shadow-sm"
    >
      {/* Header row */}
      <div
        className="grid items-center border-b border-border bg-background/40"
        style={{ gridTemplateColumns: GRID_TEMPLATE }}
      >
        <div className="px-4 py-3">
          <div className="h-3 w-16 rounded bg-border" />
        </div>
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="flex justify-center px-3 py-3">
            <div className="h-3 w-12 rounded bg-border" />
          </div>
        ))}
      </div>

      {/* Section rows */}
      {Array.from({ length: ROWS }).map((_, row) => (
        <div
          key={row}
          className="grid items-center border-b border-border last:border-b-0"
          style={{ gridTemplateColumns: GRID_TEMPLATE }}
        >
          <div className="px-4 py-3">
            <div className="h-4 w-2/3 rounded bg-border" />
          </div>
          {Array.from({ length: 4 }).map((_, cell) => (
            <div key={cell} className="flex justify-center px-3 py-3">
              <div className="h-4 w-10 rounded bg-border" />
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}
