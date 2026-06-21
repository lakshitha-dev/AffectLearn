/**
 * Loading placeholder for {@link StatCard}, matching its panel shape.
 * Mirrors the `CourseCardSkeleton` pattern (animate-pulse + bg-border blocks,
 * role="status"). NOT a spinner — skeletons are an explicit AC requirement.
 */
export function StatCardSkeleton() {
  return (
    <div
      role="status"
      aria-label="Loading metric"
      className="animate-pulse rounded-xl border border-border bg-surface p-6 shadow-sm"
    >
      <div className="h-4 w-24 rounded bg-border" />
      <div className="mt-3 h-8 w-20 rounded bg-border" />
      <div className="mt-4 h-3 w-28 rounded bg-border" />
    </div>
  );
}
