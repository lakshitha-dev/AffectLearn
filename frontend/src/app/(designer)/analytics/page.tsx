export default function AnalyticsPage() {
  const heatmapData = [
    { section: "1.1 Introduction to Networks", engaged: 82, confused: 8, bored: 7, frustrated: 3 },
    { section: "1.2 OSI Model Overview", engaged: 71, confused: 14, bored: 9, frustrated: 6 },
    { section: "1.3 TCP/IP Protocol Stack", engaged: 54, confused: 32, bored: 5, frustrated: 9 },
    { section: "2.1 Subnetting Basics", engaged: 38, confused: 44, bored: 4, frustrated: 14 },
    { section: "2.2 CIDR Notation", engaged: 29, confused: 51, bored: 3, frustrated: 17 },
    { section: "2.3 Practice Exercises", engaged: 67, confused: 18, bored: 6, frustrated: 9 },
  ];

  const AFFECT_COLORS: Record<string, string> = {
    engaged: "bg-green-500",
    confused: "bg-amber-500",
    bored: "bg-slate-400",
    frustrated: "bg-red-500",
  };

  function intensityClass(value: number): string {
    if (value >= 60) return "opacity-100";
    if (value >= 40) return "opacity-70";
    if (value >= 20) return "opacity-40";
    return "opacity-20";
  }

  return (
    <div>
      <div className="mb-8">
        <h1 className="text-2xl font-bold text-foreground">Course Analytics</h1>
        <p className="mt-1 text-sm text-muted-foreground">
          Affect distribution across learners and content sections
        </p>
      </div>

      <div className="grid grid-cols-4 gap-4 mb-8">
        {[
          { label: "Active Learners", value: "36", sub: "this week", color: "text-blue-600" },
          { label: "Avg Completion Rate", value: "74%", sub: "across modules", color: "text-green-600" },
          { label: "Avg Engagement", value: "58%", sub: "in session", color: "text-purple-600" },
          { label: "Confusion Hotspots", value: "3", sub: "sections > 40%", color: "text-amber-600" },
        ].map((stat) => (
          <div key={stat.label} className="rounded-lg border border-border bg-surface p-4">
            <p className="text-sm text-muted-foreground">{stat.label}</p>
            <p className={`mt-1 text-2xl font-bold ${stat.color}`}>{stat.value}</p>
            <p className="text-xs text-muted-foreground">{stat.sub}</p>
          </div>
        ))}
      </div>

      <div className="rounded-lg border border-border bg-surface overflow-hidden">
        <div className="border-b border-border bg-background px-5 py-3 flex items-center justify-between">
          <h2 className="font-semibold text-foreground">Affect Heatmap — Module 1 &amp; 2</h2>
          <div className="flex items-center gap-4 text-xs text-muted-foreground">
            {Object.entries(AFFECT_COLORS).map(([affect, colorClass]) => (
              <span key={affect} className="flex items-center gap-1.5 capitalize">
                <span className={`h-2.5 w-2.5 rounded-sm ${colorClass}`} />
                {affect}
              </span>
            ))}
          </div>
        </div>
        <table className="w-full text-sm" role="grid" aria-label="Affect distribution by section">
          <thead>
            <tr className="border-b border-border">
              <th className="px-5 py-3 text-left font-medium text-muted-foreground w-64">Section</th>
              <th className="px-3 py-3 text-center font-medium text-muted-foreground">Engaged %</th>
              <th className="px-3 py-3 text-center font-medium text-muted-foreground">Confused %</th>
              <th className="px-3 py-3 text-center font-medium text-muted-foreground">Bored %</th>
              <th className="px-3 py-3 text-center font-medium text-muted-foreground">Frustrated %</th>
            </tr>
          </thead>
          <tbody>
            {heatmapData.map((row, i) => (
              <tr
                key={row.section}
                className={`border-b border-border last:border-0 cursor-pointer transition-colors hover:bg-background/70 ${i % 2 === 0 ? "" : "bg-background/30"}`}
              >
                <td className="px-5 py-3 text-foreground font-medium text-xs">{row.section}</td>
                {(["engaged", "confused", "bored", "frustrated"] as const).map((affect) => {
                  const val = row[affect];
                  return (
                    <td key={affect} className="px-3 py-3 text-center">
                      <span
                        className={`inline-flex items-center justify-center rounded px-2 py-0.5 text-xs font-semibold text-white ${AFFECT_COLORS[affect]} ${intensityClass(val)}`}
                      >
                        {val}%
                      </span>
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <p className="mt-3 text-xs text-muted-foreground text-right">
        Based on 36 learners · 142 total sessions · Updated 10 min ago
      </p>
    </div>
  );
}
