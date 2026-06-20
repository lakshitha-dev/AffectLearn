export default function AnalyticsPage() {
  // Affect distribution analytics are derived from collected research events
  // (facial/behavioral/multimodal affect per section). Until sessions have been
  // recorded there is nothing to aggregate, so this page shows an honest empty
  // state rather than placeholder data. A real aggregation endpoint over
  // `research_events` / `section_progress` will populate the heatmap below.
  const AFFECT_COLORS: Record<string, string> = {
    engaged: "bg-green-500",
    confused: "bg-amber-500",
    bored: "bg-slate-400",
    frustrated: "bg-red-500",
  };

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-foreground">Course Analytics</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Affect distribution across learners and content sections
        </p>
      </div>

      <div className="rounded-lg border border-border bg-surface overflow-hidden">
        <div className="border-b border-border bg-background px-5 py-3 flex items-center justify-between">
          <h2 className="font-semibold text-foreground">Affect Heatmap</h2>
          <div className="flex items-center gap-4 text-xs text-muted-foreground">
            {Object.entries(AFFECT_COLORS).map(([affect, colorClass]) => (
              <span key={affect} className="flex items-center gap-1.5 capitalize">
                <span className={`h-2.5 w-2.5 rounded-sm ${colorClass}`} />
                {affect}
              </span>
            ))}
          </div>
        </div>

        <div className="px-5 py-16 text-center">
          <p className="text-sm font-medium text-foreground">No affect data yet</p>
          <p className="mx-auto mt-2 max-w-md text-sm text-muted-foreground">
            Per-section engagement, confusion, boredom, and frustration will appear here
            once learners complete sessions and affect events are collected.
          </p>
        </div>
      </div>
    </div>
  );
}
