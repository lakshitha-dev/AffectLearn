/**
 * Loading placeholder for a course row in the dashboard per-course list,
 * matching the real row's shape. Mirrors the `CourseCardSkeleton` pattern
 * (animate-pulse + bg-border blocks, role="status"). NOT a spinner.
 */
export function CourseRowSkeleton() {
  return (
    <div
      role="status"
      aria-label="Loading course"
      className="flex animate-pulse items-center justify-between rounded-lg border border-border bg-surface px-5 py-4"
    >
      <div className="flex-1">
        <div className="h-5 w-1/3 rounded bg-border" />
        <div className="mt-2 h-3 w-1/2 rounded bg-border" />
      </div>
      <div className="ml-4 h-4 w-4 rounded bg-border" />
    </div>
  );
}
