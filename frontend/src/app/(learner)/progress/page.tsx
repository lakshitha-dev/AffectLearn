export default function ProgressPage() {
  const modules = [
    { name: "Module 1 — Introduction to Networks", lessons: 4, completed: 4, score: 88 },
    { name: "Module 2 — Subnetting & CIDR", lessons: 5, completed: 3, score: null },
    { name: "Module 3 — Routing Protocols", lessons: 4, completed: 0, score: null },
    { name: "Module 4 — Network Security", lessons: 5, completed: 0, score: null },
  ];

  const totalLessons = modules.reduce((s, m) => s + m.lessons, 0);
  const completedLessons = modules.reduce((s, m) => s + m.completed, 0);
  const overallProgress = Math.round((completedLessons / totalLessons) * 100);

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-foreground">My Progress</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Track your learning journey across all modules
        </p>
      </div>

      <div className="mb-8 rounded-lg border border-border bg-surface p-6">
        <div className="flex items-center justify-between mb-3">
          <h2 className="font-semibold text-foreground">Overall Progress</h2>
          <span className="text-sm font-semibold text-primary">{overallProgress}%</span>
        </div>
        <div className="h-2.5 w-full rounded-full bg-border">
          <div
            className="h-2.5 rounded-full bg-primary transition-all"
            style={{ width: `${overallProgress}%` }}
            role="progressbar"
            aria-valuenow={overallProgress}
            aria-valuemin={0}
            aria-valuemax={100}
          />
        </div>
        <p className="mt-2 text-sm text-muted-foreground">
          {completedLessons} of {totalLessons} lessons completed
        </p>
      </div>

      <div className="space-y-3">
        {modules.map((mod) => {
          const pct = mod.lessons > 0 ? Math.round((mod.completed / mod.lessons) * 100) : 0;
          const done = mod.completed === mod.lessons;
          return (
            <div key={mod.name} className="rounded-lg border border-border bg-surface p-5">
              <div className="flex items-start justify-between mb-3">
                <div className="flex items-center gap-2">
                  {done ? (
                    <span className="flex h-5 w-5 items-center justify-center rounded-full bg-green-500 text-white">
                      <svg className="h-3 w-3" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                        <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={3} d="M5 13l4 4L19 7" />
                      </svg>
                    </span>
                  ) : (
                    <span className="flex h-5 w-5 items-center justify-center rounded-full border-2 border-border text-[10px] font-semibold text-muted-foreground">
                      {pct > 0 ? "…" : ""}
                    </span>
                  )}
                  <h3 className="text-sm font-semibold text-foreground">{mod.name}</h3>
                </div>
                {mod.score !== null && (
                  <span className="text-sm font-semibold text-green-600">{mod.score}%</span>
                )}
              </div>
              <div className="flex items-center gap-3">
                <div className="flex-1 h-1.5 rounded-full bg-border">
                  <div
                    className={`h-1.5 rounded-full transition-all ${done ? "bg-green-500" : "bg-primary"}`}
                    style={{ width: `${pct}%` }}
                  />
                </div>
                <span className="text-xs text-muted-foreground shrink-0">
                  {mod.completed}/{mod.lessons} lessons
                </span>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
