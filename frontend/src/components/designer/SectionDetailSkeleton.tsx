/**
 * Loading placeholder for the section-detail view (Story 7.4, AC9).
 *
 * Mirrors the 7.2/7.3 skeleton discipline (animate-pulse + bg-border blocks,
 * role="status"). Shapes a header + the three panels (affect bars, key insights,
 * content preview) so the page does not reflow on load. NOT a spinner — skeletons
 * are an explicit AC.
 */
export function SectionDetailSkeleton() {
  return (
    <div
      role="status"
      aria-label="Loading section detail"
      className="animate-pulse space-y-6"
    >
      {/* Header */}
      <div className="space-y-2">
        <div className="h-3 w-28 rounded bg-border" />
        <div className="h-7 w-1/2 rounded bg-border" />
      </div>

      {/* Panel 1: affect bars + Panel 2: key insights (two columns) */}
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="rounded-xl border border-border bg-surface p-6 shadow-sm">
          <div className="h-4 w-32 rounded bg-border" />
          <div className="mt-5 space-y-3">
            {Array.from({ length: 4 }).map((_, i) => (
              <div key={i} className="h-3 w-full rounded bg-border" />
            ))}
          </div>
        </div>
        <div className="rounded-xl border border-border bg-surface p-6 shadow-sm">
          <div className="h-4 w-28 rounded bg-border" />
          <div className="mt-5 space-y-4">
            <div className="h-10 w-full rounded bg-border" />
            <div className="h-10 w-full rounded bg-border" />
          </div>
        </div>
      </div>

      {/* Panel 3: content preview */}
      <div className="rounded-xl border border-border bg-surface p-6 shadow-sm">
        <div className="h-4 w-36 rounded bg-border" />
        <div className="mt-5 space-y-3">
          {Array.from({ length: 5 }).map((_, i) => (
            <div key={i} className="h-4 w-full rounded bg-border" />
          ))}
        </div>
      </div>
    </div>
  );
}
