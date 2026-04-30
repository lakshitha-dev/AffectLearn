export function CourseCardSkeleton() {
  return (
    <div
      role="status"
      aria-label="Loading course"
      className="h-full animate-pulse rounded-xl border border-border bg-surface p-6 shadow-sm"
    >
      <div className="mb-3 h-5 w-3/4 rounded bg-border" />
      <div className="space-y-2">
        <div className="h-4 w-full rounded bg-border" />
        <div className="h-4 w-5/6 rounded bg-border" />
      </div>
      <div className="mt-6 flex gap-3">
        <div className="h-3 w-16 rounded bg-border" />
        <div className="h-3 w-20 rounded bg-border" />
      </div>
    </div>
  );
}
